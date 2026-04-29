# Test plan — shared-profile stock import

## What changed
The admin stock importer should now allow multiple stock entries with the same email when they represent different profiles of the same shared account, while still rejecting true duplicates for the same `email + profile` within the same product.

## Code evidence that defines the flow
- Admin login and stock routes: `config/urls.py:60-84`
- Quick-add modal UI in stock overview: `templates/admin/stock_overview.html:105-201`
- Quick-add POST handler and result messages: `config/admin_views.py:657-705`
- Duplicate detection logic for `email + profile`: `catalog/admin.py:309-542`
- Stock list shortcut from admin: `templates/admin/catalog/stock_changelist.html:1-10`

## Primary flow
1. Open `/jheliz-admin/stock/` and click `+ Agregar` on the `Netflix Premium — 1 perfil` card.
2. Paste two rows with the same email but different profile names into the modal textarea.
3. Submit and verify both rows are created by the success banner.
4. Open the stock list and search for `shared@example.com`.
5. Open the two matching rows and verify one credential block contains `Perfil: Perfil 1` and the other contains `Perfil: Perfil 2`.

## Critical edge case
6. Return to the same `+ Agregar` modal and paste one of the exact same `email + profile` rows again.
7. Verify the warning banner says the pasted account already existed and nothing new was created.

## Assertions
- The Netflix product card in `/jheliz-admin/stock/` must expose a `+ Agregar` button that opens the quick-add modal for that product.
- After pasting `shared@example.com|ClaveUno|Perfil 1|1111` and `shared@example.com|ClaveDos|Perfil 2|2222`, the banner must state `Se agregaron 2 cuenta(s) a Netflix Premium — 1 perfil.` and must **not** mention omitted duplicates.
- Searching the stock list for `shared@example.com` must return exactly 2 rows, and their saved credentials must distinguish `Perfil: Perfil 1` vs `Perfil: Perfil 2`.
- Re-pasting `shared@example.com|ClaveUno|Perfil 1|1111` must show the warning `Todas las cuentas pegadas (1) ya existían en el stock. No se creó nada nuevo.`
- If the fix were broken, the first modal submission would report only 1 or 0 created rows and/or mention duplicates on the very first import.
