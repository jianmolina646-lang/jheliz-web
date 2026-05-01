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
    cart.add(plan=item.plan, quantity=1, profile_name="", pin="", notes=f"Renovación de #{item.order.short_uuid}")
    messages.success(request, f"{item.product_name} agregado para renovar.")
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
    return render(request, "orders/cart.html", {
        "cart": cart,
        "lines": lines,
        "subtotal": subtotal,
        "discount": discount,
        "total": subtotal - discount,
        "coupon": coupon,
        "coupon_error": coupon_error,
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

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            method = form.cleaned_data["payment_method"]
            if method == "yape" and not yape_available:
                messages.error(request, "Yape no est\u00e1 disponible en este momento.")
                return redirect("orders:checkout")

            order = _create_order_from_cart(request, cart, form.cleaned_data)
            cart.clear()
            emails.send_order_received(order)
            telegram.notify_admin(telegram.format_new_order(order))

            if method == "yape":
                order.payment_provider = "yape"
                order.save(update_fields=["payment_provider"])
                return redirect("orders:yape_payment", uuid=order.uuid)

            # Default: Mercado Pago
            if mercadopago_client.is_configured():
                try:
                    preference = mercadopago_client.create_preference(request, order)
                except mercadopago_client.MercadoPagoError as exc:
                    logger.exception("Mercado Pago preference failed")
                    messages.error(
                        request,
                        f"No pudimos iniciar el pago: {exc}. Te contactaremos por correo.",
                    )
                    return redirect("orders:detail", uuid=order.uuid)

                order.payment_provider = "mercadopago"
                order.payment_reference = preference.get("id", "")
                order.save(update_fields=["payment_provider", "payment_reference"])

                init_point = preference.get("init_point")
                sandbox_init = preference.get("sandbox_init_point")
                target = init_point if not settings.DEBUG else (sandbox_init or init_point)
                if target:
                    return redirect(target)

            messages.warning(
                request,
                "Mercado Pago a\u00fan no est\u00e1 configurado. Tu pedido qued\u00f3 registrado y te contactaremos.",
            )
            return redirect("orders:detail", uuid=order.uuid)
    else:
        form = CheckoutForm(initial=initial)
        if not yape_available:
            # Deja solo Mercado Pago como opci\u00f3n.
            form.fields["payment_method"].choices = [CheckoutForm.PAYMENT_METHODS[0]]

    subtotal = cart.subtotal_for(request.user)
    discount = cart.discount_for(request.user)
    return render(request, "orders/checkout.html", {
        "form": form,
        "cart": cart,
        "lines": _decorated_lines(cart, request.user),
        "subtotal": subtotal,
        "discount": discount,
        "total": subtotal - discount,
        "coupon": cart.get_coupon(),
        "yape_available": yape_available,
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
            telegram.notify_admin(telegram.format_yape_proof(order))
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


def _create_order_from_cart(request, cart: Cart, contact: dict) -> Order:
    user = request.user if request.user.is_authenticated else None
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
        order.status = Order.Status.PREPARING
        order.paid_at = now
        update_fields += ["status", "paid_at"]
        order.save(update_fields=update_fields)
        from .auto_delivery import auto_deliver_distributor_order

        delivered, _missing = auto_deliver_distributor_order(order)
        if not delivered:
            emails.send_order_preparing(order)
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
