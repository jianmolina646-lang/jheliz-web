ALTER TABLE "Customer" ADD COLUMN "email" TEXT;
ALTER TABLE "Customer" ADD COLUMN "passwordHash" TEXT;
CREATE UNIQUE INDEX "Customer_email_key" ON "Customer"("email");
