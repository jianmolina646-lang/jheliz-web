from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from inventory.models import DigitalAccount
from replacements.models import Replacement
from sales.models import Sale
from services.models import DigitalService


@login_required
def home(request):
    today = timezone.localdate()
    renewal_limit = today + timezone.timedelta(days=7)
    accounts = DigitalAccount.objects.select_related("service")
    active_accounts = accounts.exclude(status=DigitalAccount.Status.RETIRED)
    renewal_accounts = accounts.filter(
        renewal_date__range=(today, renewal_limit)
    ).exclude(status__in=(DigitalAccount.Status.RETIRED, DigitalAccount.Status.SOLD))
    attention_accounts = accounts.filter(
        status__in=(
            DigitalAccount.Status.REVIEW,
            DigitalAccount.Status.BLOCKED,
            DigitalAccount.Status.EXPIRED,
        )
    )

    month_starts = []
    cursor = today.replace(day=1)
    for offset in range(11, -1, -1):
        year = cursor.year
        month = cursor.month - offset
        while month <= 0:
            year -= 1
            month += 12
        month_starts.append(cursor.replace(year=year, month=month))
    sales_by_month = {
        row["month"].date(): row["total"] or 0
        for row in Sale.objects.filter(sold_at__date__gte=month_starts[0])
        .annotate(month=TruncMonth("sold_at"))
        .values("month")
        .annotate(total=Sum("amount"))
    }
    revenue = [sales_by_month.get(month, 0) for month in month_starts]
    max_revenue = max(revenue, default=0) or 1
    revenue_points = " ".join(
        f"{index * 100 / 11:.1f},{40 - float(value) * 34 / float(max_revenue):.1f}"
        for index, value in enumerate(revenue)
    )
    month_labels = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
    revenue_months = [month_labels[month.month - 1] for month in month_starts]
    current_month_sales = Sale.objects.filter(
        sold_at__year=today.year, sold_at__month=today.month
    )
    monthly_revenue = current_month_sales.aggregate(total=Sum("amount"))["total"] or 0
    monthly_sales_count = current_month_sales.count()
    average_ticket = monthly_revenue / monthly_sales_count if monthly_sales_count else 0
    total_accounts = active_accounts.count()
    sold_accounts = accounts.filter(status=DigitalAccount.Status.SOLD).count()
    occupancy = sold_accounts * 100 / total_accounts if total_accounts else 0

    platforms = list(
        DigitalService.objects.filter(is_active=True)
        .annotate(
            account_total=Count("accounts", filter=~Q(accounts__status=DigitalAccount.Status.RETIRED)),
            sold_total=Count("accounts", filter=Q(accounts__status=DigitalAccount.Status.SOLD)),
        )
        .filter(account_total__gt=0)
        .order_by("-account_total", "name")[:5]
    )
    for platform in platforms:
        platform.occupancy = round(platform.sold_total * 100 / platform.account_total)

    upcoming_renewals = list(renewal_accounts.order_by("renewal_date")[:4])
    for account in upcoming_renewals:
        days = (account.renewal_date - today).days
        account.renewal_caption = "Hoy" if days == 0 else f"En {days} días"
        account.renewal_tone = "danger" if days == 0 else "warning"

    activities = []
    for sale in Sale.objects.select_related("account__service").order_by("-sold_at")[:4]:
        activities.append({"date": sale.sold_at, "title": "Venta registrada", "detail": f"{sale.account.service.name} · S/ {sale.amount}"})
    for replacement in Replacement.objects.select_related("replacement_account__service").order_by("-replaced_at")[:4]:
        activities.append({"date": replacement.replaced_at, "title": "Cuenta repuesta", "detail": f"{replacement.replacement_account.service.name} · {replacement.replacement_account.masked_email}"})
    for account in accounts.order_by("-created_at")[:4]:
        activities.append({"date": account.created_at, "title": "Nueva cuenta añadida", "detail": account.service.name})
    activities = sorted(activities, key=lambda item: item["date"], reverse=True)[:4]
    return render(
        request,
        "dashboard/home.html",
        {
            "metrics": [
                {
                    "label": "Cuentas activas", "value": total_accounts, "tone": "primary",
                },
                {
                    "label": "Disponibles", "value": accounts.filter(status=DigitalAccount.Status.AVAILABLE).count(), "tone": "success",
                },
                {"label": "Por vencer (7d)", "value": renewal_accounts.count(), "tone": "warning"},
                {
                    "label": "Requieren atención", "value": attention_accounts.count(), "tone": "danger",
                },
            ],
            "monthly_revenue": monthly_revenue,
            "average_ticket": average_ticket,
            "occupancy": occupancy,
            "revenue_points": revenue_points,
            "revenue_months": revenue_months,
            "platforms": platforms,
            "renewal_accounts": upcoming_renewals,
            "activities": activities,
        },
    )


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "not_ready"}, status=503)
    return JsonResponse({"status": "ready"})
