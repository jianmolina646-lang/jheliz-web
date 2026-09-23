CREATE TYPE "public"."SubscriptionStatus" AS ENUM ('ACTIVE', 'EXPIRED', 'SUSPENDED');
CREATE TYPE "public"."SupportStatus" AS ENUM ('OPEN', 'REVIEWING', 'RESTORED', 'REPLACED', 'RESOLVED', 'REJECTED');

CREATE TABLE "public"."Subscription" (
    "id" TEXT NOT NULL,
    "customerId" TEXT NOT NULL,
    "productId" TEXT NOT NULL,
    "inventoryId" TEXT,
    "startsAt" TIMESTAMP(3) NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "status" "public"."SubscriptionStatus" NOT NULL DEFAULT 'ACTIVE',
    "reminderSentAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "Subscription_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "public"."SupportTicket" (
    "id" TEXT NOT NULL,
    "customerId" TEXT NOT NULL,
    "subscriptionId" TEXT,
    "reason" TEXT NOT NULL,
    "status" "public"."SupportStatus" NOT NULL DEFAULT 'OPEN',
    "replacementId" TEXT,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "SupportTicket_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "Subscription_customerId_status_idx" ON "public"."Subscription"("customerId", "status");
CREATE INDEX "Subscription_expiresAt_status_idx" ON "public"."Subscription"("expiresAt", "status");
CREATE INDEX "SupportTicket_customerId_status_idx" ON "public"."SupportTicket"("customerId", "status");

ALTER TABLE "public"."Subscription" ADD CONSTRAINT "Subscription_customerId_fkey" FOREIGN KEY ("customerId") REFERENCES "public"."Customer"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "public"."Subscription" ADD CONSTRAINT "Subscription_productId_fkey" FOREIGN KEY ("productId") REFERENCES "public"."Product"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "public"."Subscription" ADD CONSTRAINT "Subscription_inventoryId_fkey" FOREIGN KEY ("inventoryId") REFERENCES "public"."InventoryItem"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "public"."SupportTicket" ADD CONSTRAINT "SupportTicket_customerId_fkey" FOREIGN KEY ("customerId") REFERENCES "public"."Customer"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "public"."SupportTicket" ADD CONSTRAINT "SupportTicket_subscriptionId_fkey" FOREIGN KEY ("subscriptionId") REFERENCES "public"."Subscription"("id") ON DELETE SET NULL ON UPDATE CASCADE;
