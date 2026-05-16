from __future__ import annotations

import json
import logging
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from catalog.models import Plan

from . import emails, mercadopago_client, telegram
from .cart import Cart
from .forms import AddToCartForm, CheckoutForm, YapeProofForm
from .models import Coupon, Order, OrderItem, PaymentSettings

logger = logging.getLogger(__name__)


def _plan_from_request(request) -> Plan:
    plan_id = request.POST.get("plan_id") or request.GET.get("plan")
    if not plan_id:
        raise Http404
    return get_object_or_404(Plan.objects.select_related("product"), pk=plan_id, is_active=True)


def renew_item(request, item_id: int):
    """1-click renewal: add the same plan from a past OrderItem to the cart and go to checkout."""
    from django.contrib.auth.decorators import login_required as _li

    if not request.user.is_authenticated:
        return redirect("accounts:login")
    item = get_object_or_404(
        OrderItem.objects.select_related("plan__product", "order"),
        pk=item_id,
        order__user=request.user,
    )
    if not item.plan or not item.plan.is_active:
        messages.error(request, "Este plan ya no está disponible. Mira las opciones actualizadas.")
        return redirect(item.plan.product.get_absolute_url() if item.plan else "catalog:products")

    cart = Cart(request)
    cart.add(plan=item.plan, quantity=1, profile_name="", pin="", notes=f"Renovación de #{item.order.display_number}")
    messages.success(request, f"{item.product_name} agregado para renovar.")
    return redirect("orders:cart")


def renew_by_token(request, token: str):
    """Renovación por magic link (sin login).

    Este endpoint se usa desde el correo/WhatsApp de recordatorio de vencimiento:
    abrir el link agrega el mismo plan al carrito y redirige al carrito para
    que el cliente revise y pague. No requiere login — el token actúa como
    identificador; el cliente completa sus datos en checkout como siempre.
    """
    item = get_object_or_404(
        OrderItem.objects.select_related("plan__product", "order"),
        renewal_token=token,
    )
    if not item.plan or not item.plan.is_active:
        messages.error(request, "Este plan ya no está disponible. Mira las opciones actualizadas.")
        product = item.plan.product if item.plan else None
        return redirect(product.get_absolute_url() if product else "catalog:products")

    cart = Cart(request)
    cart.add(
        plan=item.plan,
        quantity=1,
        profile_name=item.requested_profile_name or "",
        pin=item.requested_pin or "",
        notes=f"Renovación de #{item.order.display_number}",
    )
    messages.success(
        request,
        f"Listo, agregamos {item.product_name} — {item.plan_name} a tu carrito para renovar.",
    )
    return redirect("orders:cart")


@require_POST
def add_to_cart(request):
    plan = _plan_from_request(request)
    form = AddToCartForm(request.POST)
    is_htmx = bool(request.headers.get("HX-Request"))

    if not form.is_valid():
        messages.error(request, "Revisa los datos del carrito.")
        if is_htmx:
            return _cart_toast(request, "Revisa los datos del carrito.", ok=False)
        return redirect(plan.product.get_absolute_url())

    qty = int(form.cleaned_data["quantity"])
    is_distributor = bool(getattr(request.user, "is_distributor", False))

    if plan.product.requires_customer_profile_data:
        # Para distribuidores con cantidad > 1, permitimos saltar el perfil/PIN
        # acá y que los completen después por línea en el carrito (uno distinto
        # para cada cliente final). Para clientes finales seguimos exigiendo
        # los datos en este paso.
        skip_profile_validation = is_distributor and qty > 1
        if not skip_profile_validation:
            missing = []
            if not form.cleaned_data["profile_name"]:
                missing.append("nombre de perfil")
            if not form.cleaned_data["pin"]:
                missing.append("PIN")
            if missing:
                msg = "Falta completar: " + ", ".join(missing) + "."
                messages.error(request, msg + " Son necesarios para crear tu perfil.")
                if is_htmx:
                    return _cart_toast(request, msg, ok=False)
                return redirect(plan.product.get_absolute_url())

    cart = Cart(request)
    needs_split = (
        plan.product.requires_customer_profile_data
        and qty > 1
        and is_distributor
    )
    if needs_split:
        # Cada copia es una línea independiente para que el distribuidor pueda
        # poner perfil/PIN distinto por cliente final.
        for _ in range(qty):
            cart.add(
                plan=plan, quantity=1,
                profile_name=form.cleaned_data["profile_name"],
                pin=form.cleaned_data["pin"],
                notes=form.cleaned_data["notes"],
            )
        success_msg = (
            f"{qty}× {plan.product.name} \u2014 {plan.name} agregadas. "
            "Completá perfil y PIN de cada una en el carrito."
        )
    else:
        cart.add(
            plan=plan,
            quantity=qty,
            profile_name=form.cleaned_data["profile_name"],
            pin=form.cleaned_data["pin"],
            notes=form.cleaned_data["notes"],
        )
        success_msg = f"{plan.product.name} \u2014 {plan.name} agregado al carrito."
    messages.success(request, success_msg)

    if is_htmx:
        # Send cart-updated event so the header counter can refresh.
        cart_count = sum(int(line.quantity) for line in cart.lines())
        response = _cart_toast(request, success_msg, ok=True, cart_count=cart_count)
        response["HX-Trigger"] = json.dumps({"cart-updated": {"count": cart_count}})
        return response
    return redirect("orders:cart")


def _cart_toast(request, text: str, ok: bool, cart_count: int | None = None):
    """Render the small toast fragment returned by the htmx add-to-cart action."""
    return render(
        request,
        "orders/_cart_toast.html",
        {"toast_text": text, "toast_ok": ok, "cart_count": cart_count},
    )


def _decorated_lines(cart: Cart, user) -> list:
    out = []
    for line in cart.lines():
        line.unit_price_for_user = line.price_for(user)
        line.subtotal_for_user = line.subtotal_for(user)
        out.append(line)
    return out


def cart_view(request):
    cart = Cart(request)
    lines = _decorated_lines(cart, request.user)
    subtotal = cart.subtotal_for(request.user)
    coupon = cart.get_coupon()
    discount = cart.discount_for(request.user)
    coupon_error = ""
    if coupon and discount == 0 and not cart.is_empty():
        # Cupón inválido en este momento: avisa al cliente.
        ok, msg = coupon.is_eligible_for(request.user, subtotal)
        if not ok:
            coupon_error = msg
    combo_discount = cart.combo_discount_for(request.user)
    combo_pct = cart.combo_tier_percent()
    distinct_products = cart.distinct_product_count()
    # Si el carrito está vacío, sugerimos los 4 destacados para que el cliente
    # no se quede en una página muerta.
    suggested = []
    if cart.is_empty():
        from catalog.models import Product
        suggested = list(
            Product.objects.filter(is_active=True, is_featured=True)
            .select_related("category")
            .order_by("-id")[:4]
        )
        if len(suggested) < 4:
            extra = (
                Product.objects.filter(is_active=True)
                .exclude(id__in=[p.id for p in suggested])
                .select_related("category")
                .order_by("-id")[: 4 - len(suggested)]
            )
            suggested.extend(list(extra))
    return render(request, "orders/cart.html", {
        "cart": cart,
        "lines": lines,
        "subtotal": subtotal,
        "discount": discount,
        "combo_discount": combo_discount,
        "combo_percent_int": int(combo_pct * 100) if combo_pct else 0,
        "distinct_products": distinct_products,
        "total": subtotal - discount - combo_discount,
        "coupon": coupon,
        "coupon_error": coupon_error,
        "suggested_products": suggested,
    })


@require_POST
def cart_apply_coupon(request):
    cart = Cart(request)
    code = (request.POST.get("code") or "").strip().upper()
    if not code:
        cart.clear_coupon()
        messages.info(request, "Cupón retirado.")
        return redirect("orders:cart")

    coupon = Coupon.objects.filter(code=code).first()
    if not coupon:
        messages.error(request, f"El cupón '{code}' no existe.")
        return redirect("orders:cart")

    subtotal = cart.subtotal_for(request.user)
    ok, msg = coupon.is_eligible_for(request.user, subtotal)
    if not ok:
        messages.error(request, msg or "Este cupón no aplica a tu carrito.")
        return redirect("orders:cart")

    cart.set_coupon_code(coupon.code)
    discount = coupon.compute_discount(subtotal)
    messages.success(request, f"Cupón {coupon.code} aplicado: descuento de S/ {discount:g}.")
    return redirect("orders:cart")


@require_POST
def cart_remove_coupon(request):
    Cart(request).clear_coupon()
    messages.info(request, "Cupón retirado del carrito.")
    return redirect("orders:cart")


@require_POST
def cart_remove(request, index: int):
    Cart(request).remove(int(index))
    messages.info(request, "Item eliminado del carrito.")
    return redirect("orders:cart")


@require_POST
def cart_clear(request):
    Cart(request).clear()
    return redirect("orders:cart")


@require_POST
def cart_update_line(request, index: int):
    """Actualiza perfil/PIN/notas/cantidad de una línea ya existente del carrito.

    Pensado sobre todo para que el distribuidor que compró N copias del mismo
    plan pueda completar el perfil de cada cliente final desde el carrito.
    """
    cart = Cart(request)
    profile_name = (request.POST.get("profile_name") or "").strip()[:60]
    pin = (request.POST.get("pin") or "").strip()[:8]
    notes = (request.POST.get("notes") or "").strip()[:500]
    fields = {"profile_name": profile_name, "pin": pin, "notes": notes}
    raw_qty = request.POST.get("quantity")
    if raw_qty is not None:
        try:
            qty = max(1, min(50, int(raw_qty)))
            fields["quantity"] = qty
        except (TypeError, ValueError):
            pass
    cart.update_line(int(index), **fields)
    messages.success(request, "Línea del carrito actualizada.")
    return redirect("orders:cart")


@require_POST
def cart_duplicate_line(request, index: int):
    """Duplica una línea del carrito (útil para distribuidores que quieren +1 igual)."""
    cart = Cart(request)
    idx = int(index)
    if 0 <= idx < len(cart._items):
        original = dict(cart._items[idx])
        # vacía perfil/pin para que el distribuidor llene los datos del cliente nuevo
        original["profile_name"] = ""
        original["pin"] = ""
        cart._items.insert(idx + 1, original)
        cart.save()
        messages.success(request, "Línea duplicada — completá perfil y PIN del nuevo cliente.")
    return redirect("orders:cart")


def checkout(request):
    cart = Cart(request)
    if cart.is_empty():
        messages.info(request, "Tu carrito est\u00e1 vac\u00edo.")
        return redirect("catalog:products")

    initial = {}
    if request.user.is_authenticated:
        initial = {
            "full_name": request.user.get_full_name() or request.user.username,
            "email": request.user.email,
            "phone": getattr(request.user, "phone", ""),
        }

    payment_settings = PaymentSettings.load()
    yape_available = bool(payment_settings.yape_enabled and payment_settings.yape_qr)
    binance_available = bool(
        payment_settings.binance_enabled
        and (payment_settings.binance_qr or payment_settings.binance_pay_id)
    )
    mp_checkout_enabled = bool(getattr(settings, "MERCADOPAGO_CHECKOUT_ENABLED", True))

    user_balance = Decimal("0")
    wallet_available = False
    if request.user.is_authenticated:
        user_balance = request.user.wallet_balance or Decimal("0")
        wallet_available = user_balance > Decimal("0")

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            method = form.cleaned_data["payment_method"]
            if method == "mercadopago" and not mp_checkout_enabled:
                if yape_available:
                    messages.info(
                        request,
                        "Mercado Pago no est\u00e1 disponible. Te llevamos a pagar con Yape.",
                    )
                    method = "yape"
                else:
                    messages.error(
                        request,
                        "Mercado Pago no est\u00e1 disponible en este momento.",
                    )
                    return redirect("orders:checkout")
            if method == "yape" and not yape_available:
                messages.error(request, "Yape no est\u00e1 disponible en este momento.")
                return redirect("orders:checkout")
            if method == "binance" and not binance_available:
                messages.error(request, "Binance Pay no est\u00e1 disponible en este momento.")
                return redirect("orders:checkout")
            if method == "wallet" and not request.user.is_authenticated:
                messages.error(request, "Necesitás iniciar sesión para pagar con saldo.")
                return redirect("accounts:login")

            cart_total = cart.subtotal_for(request.user) - cart.discount_for(request.user) - cart.combo_discount_for(request.user)
            if method == "wallet":
                if not wallet_available:
                    messages.error(request, "No tenés saldo en tu wallet. Recordá recargar primero.")
                    return redirect("orders:checkout")
                if user_balance < cart_total:
                    messages.error(
                        request,
                        f"Saldo insuficiente. Necesitás S/ {cart_total:,.2f} y tenés S/ {user_balance:,.2f}. Recordá recargar tu wallet.",
                    )
                    return redirect("orders:checkout")

            order = _create_order_from_cart(request, cart, form.cleaned_data)
            cart.clear()
            emails.send_order_received(order)
            telegram.notify_admin_about_order(order)

            if method == "wallet":
                from accounts.wallet import charge_for_order, InsufficientFundsError
                try:
                    charge_for_order(request.user, order.total, order)
                except InsufficientFundsError as exc:
                    messages.error(request, str(exc))
                    return redirect("orders:detail", uuid=order.uuid)
                order.payment_provider = "wallet"
                order.status = Order.Status.PAID
                order.paid_at = timezone.now()
                order.save(update_fields=["payment_provider", "status", "paid_at"])
                messages.success(
                    request,
                    f"Pagaste S/ {order.total:,.2f} con tu wallet. Pedido en preparación.",
                )
                return redirect("orders:detail", uuid=order.uuid)

            if method == "yape":
                order.payment_provider = "yape"
                order.save(update_fields=["payment_provider"])
                return redirect("orders:yape_payment", uuid=order.uuid)

            if method == "binance":
                order.payment_provider = "binance"
                order.save(update_fields=["payment_provider"])
                return redirect("orders:binance_payment", uuid=order.uuid)

            # Default: Mercado Pago. Si falla (token vencido, cuenta sin
            # habilitar, error transitorio del SDK), no dejamos al cliente
            # tirado en una pantalla genérica: lo mandamos a Yape si está
            # habilitado, así puede pagar de inmediato. Si tampoco hay Yape,
            # mostramos el detalle del pedido con instrucciones claras.
            mp_failed = False
            mp_error_msg = ""
            if mercadopago_client.is_configured():
                try:
                    preference = mercadopago_client.create_preference(request, order)
                except mercadopago_client.MercadoPagoError as mp_exc:
                    logger.exception("Mercado Pago preference failed")
                    mp_failed = True
                    mp_error_msg = str(mp_exc)[:300]
                    # Persistimos el error en las notas del pedido para que el
                    # admin vea exactamente qué dijo MP sin tener que ir a logs.
                    try:
                        order.notes = (
                            (order.notes or "")
                            + f"\n[MP ERROR] {mp_error_msg}"
                        )[:2000]
                        order.save(update_fields=["notes"])
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    order.payment_provider = "mercadopago"
                    order.payment_reference = preference.get("id", "")
                    order.save(update_fields=["payment_provider", "payment_reference"])

                    init_point = preference.get("init_point")
                    sandbox_init = preference.get("sandbox_init_point")
                    target = init_point if not settings.DEBUG else (sandbox_init or init_point)
                    if target:
                        return redirect(target)

            if mp_failed and yape_available:
                # Failover automático a Yape — el cliente igual puede pagar.
                order.payment_provider = "yape"
                order.save(update_fields=["payment_provider"])
                messages.warning(
                    request,
                    "Mercado Pago no respondió en este momento. "
                    "Te redirigimos a pagar con Yape para que no esperes.",
                )
                return redirect("orders:yape_payment", uuid=order.uuid)

            if mp_failed:
                detail = f" ({mp_error_msg})" if mp_error_msg else ""
                messages.error(
                    request,
                    "No pudimos iniciar el pago con Mercado Pago" + detail + ". "
                    "Tu pedido quedó registrado y un asesor te escribirá por WhatsApp "
                    "con un link alternativo.",
                )
                return redirect("orders:detail", uuid=order.uuid)

            messages.warning(
                request,
                "Mercado Pago a\u00fan no est\u00e1 configurado. Tu pedido qued\u00f3 registrado y te contactaremos.",
            )
            return redirect("orders:detail", uuid=order.uuid)
    else:
        form = CheckoutForm(initial=initial)

    # Construir choices del payment_method dinámicamente según disponibilidad.
    # Filtramos yape si no hay QR configurado, wallet si el usuario no tiene
    # saldo, y mercadopago si MERCADOPAGO_CHECKOUT_ENABLED está en False.
    available_methods = []
    for value, label in CheckoutForm.PAYMENT_METHODS:
        if value == "yape" and not yape_available:
            continue
        if value == "binance" and not binance_available:
            continue
        if value == "wallet" and not wallet_available:
            continue
        if value == "mercadopago" and not mp_checkout_enabled:
            continue
        available_methods.append((value, label))
    form.fields["payment_method"].choices = available_methods
    # Si MP está deshabilitado y el initial sigue siendo "mercadopago", el
    # radio queda sin opción seleccionada por defecto. Forzamos yape como
    # default para que el cliente no tenga que clickear nada.
    if not mp_checkout_enabled and yape_available:
        form.fields["payment_method"].initial = "yape"
        if not form.is_bound:
            form.initial["payment_method"] = "yape"

    subtotal = cart.subtotal_for(request.user)
    discount = cart.discount_for(request.user)
    combo_discount = cart.combo_discount_for(request.user)
    combo_pct = cart.combo_tier_percent()
    cart_total = subtotal - discount - combo_discount
    return render(request, "orders/checkout.html", {
        "form": form,
        "cart": cart,
        "lines": _decorated_lines(cart, request.user),
        "subtotal": subtotal,
        "discount": discount,
        "combo_discount": combo_discount,
        "combo_percent_int": int(combo_pct * 100) if combo_pct else 0,
        "total": cart_total,
        "coupon": cart.get_coupon(),
        "yape_available": yape_available,
        "binance_available": binance_available,
        "wallet_available": wallet_available,
        "wallet_balance": user_balance,
        "wallet_enough": wallet_available and user_balance >= cart_total,
        "payment_settings": payment_settings,
    })


def yape_payment(request, uuid):
    """Pantalla para subir comprobante Yape."""
    order = get_object_or_404(Order, uuid=uuid)
    payment_settings = PaymentSettings.load()

    if order.user_id and request.user.is_authenticated and order.user_id != request.user.id:
        if not request.user.is_staff:
            raise Http404

    if order.status not in {Order.Status.PENDING, Order.Status.VERIFYING}:
        return redirect("orders:detail", uuid=order.uuid)

    if request.method == "POST":
        form = YapeProofForm(request.POST, request.FILES)
        if form.is_valid():
            order.payment_proof = form.cleaned_data["proof"]
            order.payment_proof_uploaded_at = timezone.now()
            order.status = Order.Status.VERIFYING
            order.payment_provider = "yape"
            order.payment_rejection_reason = ""
            order.save(update_fields=[
                "payment_proof", "payment_proof_uploaded_at",
                "status", "payment_provider", "payment_rejection_reason",
            ])
            emails.send_yape_proof_received(order)
            telegram.notify_admin_about_yape(order)
            messages.success(
                request,
                "Recibimos tu comprobante. En menos de 30 minutos lo verificamos y te avisamos por correo.",
            )
            return redirect("orders:detail", uuid=order.uuid)
    else:
        form = YapeProofForm()

    return render(request, "orders/yape_payment.html", {
        "order": order,
        "form": form,
        "settings": payment_settings,
    })


def binance_payment(request, uuid):
    """Pantalla para subir comprobante de Binance Pay (mismo flujo que Yape)."""
    order = get_object_or_404(Order, uuid=uuid)
    payment_settings = PaymentSettings.load()

    if order.user_id and request.user.is_authenticated and order.user_id != request.user.id:
        if not request.user.is_staff:
            raise Http404

    if order.status not in {Order.Status.PENDING, Order.Status.VERIFYING}:
        return redirect("orders:detail", uuid=order.uuid)

    if request.method == "POST":
        form = YapeProofForm(request.POST, request.FILES)
        if form.is_valid():
            order.payment_proof = form.cleaned_data["proof"]
            order.payment_proof_uploaded_at = timezone.now()
            order.status = Order.Status.VERIFYING
            order.payment_provider = "binance"
            order.payment_rejection_reason = ""
            order.save(update_fields=[
                "payment_proof", "payment_proof_uploaded_at",
                "status", "payment_provider", "payment_rejection_reason",
            ])
            emails.send_yape_proof_received(order)
            telegram.notify_admin_about_yape(order)
            messages.success(
                request,
                "Recibimos tu comprobante de Binance. En menos de 30 minutos lo verificamos y te avisamos por correo.",
            )
            return redirect("orders:detail", uuid=order.uuid)
    else:
        form = YapeProofForm()

    # Calculo del equivalente en USD para mostrar al cliente.
    usd_amount = None
    if payment_settings.usd_exchange_rate and payment_settings.usd_exchange_rate > 0:
        usd_amount = (order.total / payment_settings.usd_exchange_rate).quantize(Decimal("0.01"))

    return render(request, "orders/binance_payment.html", {
        "order": order,
        "form": form,
        "settings": payment_settings,
        "usd_amount": usd_amount,
    })


@csrf_exempt
@require_POST
def telegram_webhook(request, secret: str):
    """Endpoint que recibe updates de Telegram (mensajes y callback queries).

    Telegram también envía un header ``X-Telegram-Bot-Api-Secret-Token`` que
    debe coincidir con ``settings.TELEGRAM_WEBHOOK_SECRET``. Validamos ambos
    (path y header) para evitar spoofing.
    """
    expected = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") or ""
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not expected or secret != expected or header != expected:
        return HttpResponse(status=403)
    update = telegram.parse_update_payload(request.body)
    if not update:
        return HttpResponse(status=400)
    try:
        telegram.process_update(update)
    except Exception:
        logger.exception("Error procesando update de Telegram")
    return HttpResponse(status=200)


def _create_order_from_cart(request, cart: Cart, contact: dict) -> Order:
    if request.user.is_authenticated:
        user = request.user
    else:
        # Auto-creamos (o reutilizamos) un User cliente para que el comprador
        # aparezca en "Zona de clientes" del admin. El User queda sin password
        # utilizable hasta que reclame la cuenta vía reseteo de contraseña.
        # Ver accounts/guest_signup.py.
        from accounts.guest_signup import get_or_create_guest_user
        try:
            user = get_or_create_guest_user(
                email=contact["email"],
                full_name=contact.get("full_name", ""),
                phone=contact.get("phone", ""),
            )
        except Exception:
            logger.exception(
                "No se pudo auto-crear User invitado; pedido queda sin user."
            )
            user = None
    with transaction.atomic():
        order = Order.objects.create(
            user=user,
            email=contact["email"],
            phone=contact.get("phone", ""),
            channel=Order.Channel.WEB,
            status=Order.Status.PENDING,
            total=Decimal("0.00"),
            currency=settings.DEFAULT_CURRENCY,
            notes=(
                f"Nombre comprador: {contact.get('full_name', '')}"
            ),
        )
        for line in cart.lines():
            unit_price = line.price_for(request.user)
            OrderItem.objects.create(
                order=order,
                product=line.plan.product,
                plan=line.plan,
                product_name=line.plan.product.name,
                plan_name=line.plan.name,
                unit_price=unit_price,
                quantity=line.quantity,
                requested_profile_name=line.profile_name,
                requested_pin=line.pin,
                customer_notes=line.notes,
            )
        # Aplicar cupón si hay y sigue siendo elegible.
        coupon = cart.get_coupon()
        if coupon:
            subtotal = order.subtotal
            ok, _msg = coupon.is_eligible_for(request.user, subtotal)
            if ok:
                order.coupon = coupon
                order.coupon_code = coupon.code
                order.discount_amount = coupon.compute_discount(subtotal)
                order.save(update_fields=["coupon", "coupon_code", "discount_amount"])
                # Bumpea el contador de usos del cupón (atomic).
                Coupon.objects.filter(pk=coupon.pk).update(times_used=models.F("times_used") + 1)
        # Aplicar descuento por combo (auto, sobre subtotal post-cupón).
        combo = cart.combo_discount_for(request.user)
        if combo > 0:
            order.combo_discount_amount = combo
            order.save(update_fields=["combo_discount_amount"])
        order.recompute_total()
    return order


def order_detail(request, uuid):
    order = get_object_or_404(Order, uuid=uuid)
    # Si el pedido tiene due\u00f1o autenticado, requerir login y match.
    if order.user_id:
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        if order.user_id != request.user.id and not request.user.is_staff:
            raise Http404
    return render(request, "orders/detail.html", {"order": order})


def order_receipt_pdf(request, uuid):
    """Descarga directa del recibo PDF del pedido (no oficial SUNAT)."""
    order = get_object_or_404(Order, uuid=uuid)
    if order.user_id:
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        if order.user_id != request.user.id and not request.user.is_staff:
            raise Http404
    from .receipts import generate_receipt_pdf, receipt_filename
    pdf_bytes = generate_receipt_pdf(order)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{receipt_filename(order)}"'
    return resp


def checkout_return(request, uuid):
    """Pantalla a la que vuelve el cliente desde Mercado Pago."""
    order = get_object_or_404(Order, uuid=uuid)
    mp_status = request.GET.get("status") or request.GET.get("collection_status") or ""
    return render(request, "orders/checkout_return.html", {
        "order": order,
        "mp_status": mp_status,
    })


@csrf_exempt
@require_POST
def mercadopago_webhook(request):
    """Recibe notificaciones de Mercado Pago y actualiza el pedido.

    Si ``MERCADOPAGO_WEBHOOK_SECRET`` está configurado, exige firma HMAC
    válida (header ``x-signature``). Si no está configurado, deja pasar
    pero loguea un warning para que el operador termine el setup.
    """
    secret = getattr(settings, "MERCADOPAGO_WEBHOOK_SECRET", "") or ""
    # data.id viaja en la query string del webhook de MP. Lo necesitamos
    # *antes* del JSON para validar la firma — el manifest se construye
    # con este valor.
    data_id_qs = request.GET.get("data.id") or request.GET.get("id") or ""
    if secret:
        ok = mercadopago_client.verify_webhook_signature(
            signature_header=request.headers.get("x-signature", ""),
            request_id=request.headers.get("x-request-id", ""),
            data_id=data_id_qs,
            secret=secret,
        )
        if not ok:
            logger.warning(
                "MP webhook con firma inválida (request-id=%s)",
                request.headers.get("x-request-id", ""),
            )
            return HttpResponse(status=401)
    else:
        logger.warning(
            "MERCADOPAGO_WEBHOOK_SECRET no configurado — "
            "el webhook de Mercado Pago acepta cualquier POST."
        )

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}

    payment_id = (
        payload.get("data", {}).get("id")
        or data_id_qs
    )
    if not payment_id:
        return HttpResponse(status=200)

    try:
        payment = mercadopago_client.fetch_payment(str(payment_id))
    except mercadopago_client.MercadoPagoError:
        logger.exception("No se pudo recuperar el pago %s", payment_id)
        return HttpResponse(status=200)

    external_reference = payment.get("external_reference") or ""
    status = payment.get("status")  # approved / pending / rejected / in_process
    if not external_reference:
        logger.warning("Webhook sin external_reference (payment_id=%s)", payment_id)
        return HttpResponse(status=200)
    try:
        order = Order.objects.get(uuid=external_reference)
    except (Order.DoesNotExist, ValueError, ValidationError):
        logger.warning("Webhook sin order matching: %s", external_reference)
        return HttpResponse(status=200)

    _apply_payment_status(order, status, payment_id)
    return JsonResponse({"ok": True})


def _apply_payment_status(order: Order, status: str, payment_id: str) -> None:
    now = timezone.now()
    update_fields = ["payment_reference"]
    order.payment_reference = str(payment_id)

    if status == "approved" and order.status != Order.Status.DELIVERED:
        # Persistimos primero el payment_reference para que la auto-entrega
        # tenga el dato fresco en el pedido.
        order.save(update_fields=update_fields)
        from .auto_delivery import auto_deliver_distributor_order

        # Distribuidor con stock: pasa directo a DELIVERED (un solo email
        # de entrega). Cliente final o sin stock: cae al fallback de
        # PREPARING que dispara el correo "Estamos preparando".
        delivered, _missing = auto_deliver_distributor_order(order, paid_at=now)
        if delivered:
            return
        order.status = Order.Status.PREPARING
        order.paid_at = now
        order.save(update_fields=["status", "paid_at"])
        return

    if status in {"pending", "in_process", "authorized"}:
        if order.status == Order.Status.PENDING:
            # sigue esperando confirmaci\u00f3n
            order.save(update_fields=update_fields)
        return

    if status in {"rejected", "cancelled", "refunded", "charged_back"}:
        order.status = Order.Status.FAILED if status == "rejected" else Order.Status.CANCELED
        update_fields.append("status")
        order.save(update_fields=update_fields)
        return

    order.save(update_fields=update_fields)
