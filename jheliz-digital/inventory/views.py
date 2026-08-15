from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from services.models import DigitalService

from accounts.permissions import inventory_manager_required

from .forms import DigitalAccountForm
from .models import DigitalAccount


@login_required
def account_list(request):
    all_accounts = DigitalAccount.objects.select_related("service", "created_by")
    today = timezone.localdate()
    renewal_limit = today + timedelta(days=7)
    month_start = today.replace(day=1)
    summary = all_accounts.aggregate(
        total=Count("pk"),
        available=Count("pk", filter=Q(status=DigitalAccount.Status.AVAILABLE)),
        sold=Count("pk", filter=Q(status=DigitalAccount.Status.SOLD)),
        renewing=Count(
            "pk",
            filter=Q(renewal_date__range=(today, renewal_limit))
            & ~Q(status__in=(DigitalAccount.Status.RETIRED, DigitalAccount.Status.SOLD)),
        ),
        overdue=Count(
            "pk",
            filter=Q(renewal_date__lt=today)
            & ~Q(status__in=(DigitalAccount.Status.RETIRED, DigitalAccount.Status.SOLD)),
        ),
        featured=Count("pk", filter=Q(is_featured=True)),
        created_this_month=Count("pk", filter=Q(created_at__date__gte=month_start)),
    )
    total = summary["total"]
    for key in ("available", "sold", "renewing"):
        summary[f"{key}_percentage"] = round(summary[key] * 100 / total, 1) if total else 0

    accounts = all_accounts
    query = request.GET.get("q", "").strip()
    service = request.GET.get("service", "").strip()
    status = request.GET.get("status", "").strip()
    renewal = request.GET.get("renewal", "").strip()
    featured = request.GET.get("featured", "").strip()
    if query:
        accounts = accounts.filter(
            Q(email__icontains=query)
            | Q(country__icontains=query)
            | Q(service__name__icontains=query)
        )
    if service:
        accounts = accounts.filter(service__slug=service)
    if status:
        accounts = accounts.filter(status=status)
    if renewal == "overdue":
        accounts = accounts.filter(renewal_date__lt=today)
    elif renewal in {"7", "30", "60"}:
        accounts = accounts.filter(
            renewal_date__range=(today, today + timedelta(days=int(renewal)))
        )
    elif renewal == "none":
        accounts = accounts.filter(renewal_date__isnull=True)
    if featured == "1":
        accounts = accounts.filter(is_featured=True)
    accounts = accounts.order_by("service__name", "email")
    paginator = Paginator(accounts, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    country_flags = {
        "argentina": "AR", "brasil": "BR", "brazil": "BR", "chile": "CL",
        "colombia": "CO", "ecuador": "EC", "egipto": "EG", "egypto": "EG", "egypt": "EG",
        "españa": "ES", "spain": "ES", "estados unidos": "US", "usa": "US",
        "méxico": "MX", "mexico": "MX", "perú": "PE", "peru": "PE",
    }
    service_domains = {
        "netflix": "netflix.com", "prime-video": "primevideo.com", "prime": "primevideo.com",
        "disney-plus": "disneyplus.com", "disney": "disneyplus.com", "hbo-max": "max.com",
        "max": "max.com", "crunchyroll": "crunchyroll.com", "spotify": "spotify.com",
        "youtube-premium": "youtube.com", "apple-tv": "tv.apple.com", "paramount-plus": "paramountplus.com",
        "canva": "canva.com", "chatgpt": "openai.com", "deezer": "deezer.com",
    }
    for account in page_obj:
        if account.renewal_date:
            days = (account.renewal_date - today).days
            if days < 0:
                account.renewal_caption = f"Vencida hace {abs(days)} días"
            elif days == 0:
                account.renewal_caption = "Vence hoy"
            else:
                account.renewal_caption = f"En {days} días"
        else:
            account.renewal_caption = "Sin fecha"
        account.display_status = account.get_status_display()
        account.display_status_class = account.status
        if account.renewal_date and account.renewal_date < today:
            account.display_status = "Vencida"
            account.display_status_class = "expired"
        elif (
            account.renewal_date
            and account.renewal_date <= renewal_limit
            and account.status == DigitalAccount.Status.AVAILABLE
        ):
            account.display_status = "Por vencer"
            account.display_status_class = "renewing"
        account.country_flag = country_flags.get(account.country.strip().lower(), "GL") if account.country else ""
        reference = account.billing_reference.strip()
        account.payment_label = account.get_billing_method_display()
        account.payment_brand = "generic"
        if account.billing_method == DigitalAccount.BillingMethod.CARD:
            lower_reference = reference.lower()
            if "visa" in lower_reference:
                account.payment_label = "Visa"
                account.payment_brand = "visa"
            elif "mastercard" in lower_reference or "master card" in lower_reference:
                account.payment_label = "Mastercard"
                account.payment_brand = "mastercard"
        account.payment_hint = f"•••• {reference[-4:]}" if reference and reference[-4:].isdigit() else (reference or "Sin referencia")
        account.logo_domain = service_domains.get(account.service.slug, f"{account.service.slug}.com")
    return render(
        request,
        "inventory/list.html",
        {
            "accounts": page_obj,
            "page_obj": page_obj,
            "summary": summary,
            "result_count": paginator.count,
            "services": DigitalService.objects.filter(is_active=True),
            "statuses": DigitalAccount.Status.choices,
            "renewal_choices": (
                ("7", "Próximos 7 días"),
                ("30", "Próximos 30 días"),
                ("60", "Próximos 60 días"),
                ("overdue", "Vencidas"),
                ("none", "Sin fecha"),
            ),
            "filters": {
                "q": query,
                "service": service,
                "status": status,
                "renewal": renewal,
                "featured": featured,
            },
        },
    )


@login_required
def account_detail(request, pk):
    account = get_object_or_404(DigitalAccount.objects.select_related("service"), pk=pk)
    return render(request, "inventory/detail.html", {"account": account})


@inventory_manager_required
def account_toggle_featured(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    account = get_object_or_404(DigitalAccount, pk=pk)
    account.is_featured = not account.is_featured
    account.save(update_fields=["is_featured"])
    query = request.POST.get("next_query", "")
    url = reverse("inventory:list")
    if query:
        url = f"{url}?{query}"
    return redirect(url)


@inventory_manager_required
def account_create(request):
    form = DigitalAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        account = form.save(commit=False)
        account.created_by = request.user
        account.save()
        return redirect("inventory:detail", pk=account.pk)
    return render(request, "inventory/form.html", {"form": form, "is_create": True})


@inventory_manager_required
def account_update(request, pk):
    account = get_object_or_404(DigitalAccount, pk=pk)
    form = DigitalAccountForm(request.POST or None, instance=account)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("inventory:detail", pk=account.pk)
    return render(request, "inventory/form.html", {"form": form, "account": account})
