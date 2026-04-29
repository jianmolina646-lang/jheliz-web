# Test report — shared-profile stock import (PR #34)

Tested locally against `main` after merge of [PR #34](https://github.com/jianmolina646-lang/jheliz-web/pull/34) using `Stock por producto → + Agregar` modal for `Netflix Premium — 1 perfil` to validate the duplicate-detection fix end-to-end.

Devin session: https://app.devin.ai/sessions/35f69e46909247cc9a1394fc24e05cbd

## Results

- It should add two shared-account profiles from the quick-add modal — **passed**
- It should reject re-adding the exact same email and profile — **passed**

No deviations from the spec were observed during testing.

## Evidence

| 🟢 Two shared profiles accepted | 🟢 Same email + same profile blocked |
|---|---|
| ![Modal pasted with 2 accounts for one email](https://app.devin.ai/attachments/0d46bf39-f60f-4eef-8cec-f3fc8fefa66d/screenshot_2b6350aaedd64930946223c3c650ae7a.png) | ![Banner: Todas las cuentas pegadas (1) ya existían](https://app.devin.ai/attachments/4ce38409-91fe-422a-bde5-6eb85fc508d6/screenshot_99096252b7324d6eae165429a721bc64.png) |
| Modal counted 2 accounts: `shared@example.com` with `Perfil 1` and `Perfil 2`. | Re-pasting `shared@example.com|ClaveUno|Perfil 1|1111` showed the warning and the available count stayed at 5. |

| 🟢 Banner after first import | 🟢 Stored credentials per row |
|---|---|
| ![Se agregaron 2 cuenta(s); Netflix 3 → 5](https://app.devin.ai/attachments/48d91214-a200-4c8d-8f0d-41b726a0813b/screenshot_920da1bb1b964df0b9f000e6284b508b.png) | ![Stock row with shared@example.com and Perfil 2](https://app.devin.ai/attachments/19af02ee-6f74-482b-a4a9-6d20d953eab1/screenshot_b11c085568814c99b570ba5ef45ee889.png) ![Stock row with shared@example.com and Perfil 1](https://app.devin.ai/attachments/183d9a94-7c78-4b2e-91bd-64c42f719aaa/screenshot_457ffd987b594624acaae1d229d49e66.png) |
| Success banner read `Se agregaron 2 cuenta(s) a Netflix Premium — 1 perfil.`, the global available counter went from 21 to 23, and the Netflix card from 3 to 5. | Two saved rows for the same product show the email `shared@example.com` paired with `Perfil 1` and `Perfil 2` in the credentials field, confirming both were persisted. |

## Notes

- Test ran on a local Django dev server with `python manage.py migrate` and `python manage.py seed_catalog`, signed in as a local superuser.
- No regression tests beyond the targeted flow were run for this PR.
