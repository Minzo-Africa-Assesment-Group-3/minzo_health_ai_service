# Available Minzo frontend routes

Use only the routes in this catalogue when directing a user to a Minzo page.
Do not invent routes or claim that a page exists when it is not listed here.

## Linking rules

- A business returned by the directory search includes `displayName` and `slug`. When mentioning a returned business, link its name as `[**Business name**](/listings/slug)`.
- Use `/listings` when directing a user to browse, search, or filter the directory themselves.
- Use the appropriate action route below when a user asks how to register, sign in, recover a password, manage their account, view followed businesses, or view their reviews.
- Do not invent a business slug, profile link, query string, or route. A business-profile link must use a `slug` returned by a tool.

- `/` — Home page. Introduces the Minzo healthcare directory and its purpose.
- `/listings` — Browse and search healthcare businesses in the directory.
- `/listings/:slug` — View a specific healthcare business profile. Replace `:slug` only with a slug returned by the Backend.
- `/account-type` — Start account registration. The user chooses whether to register as an individual or as a business.
- `/register/user` — Individual account registration. For people who want to search, review, and follow businesses.
- `/register/business` — Business account registration. For an owner or manager registering a healthcare business.
- `/login` — Sign in to an existing Minzo account.
- `/forgot-password` — Start password recovery for an existing account.

## Signed-in user routes

Only direct a signed-in user to these pages. If the user is not signed in, direct them to `/login` first.

- `/user-details` — View and update account details.
- `/user-followed` — View healthcare businesses the user follows.
- `/user-reviews` — View the user's customer reviews.
- `/user-password` — Change the user's password.
- `/user-delete` — Start account deletion.
- `/portal/dashboard` — Existing user portal dashboard.

## Portal routes

- `/portal/login` — Sign in to the existing user portal.

## Flow-only routes

These pages are part of a process and should not normally be given as a starting link:

- `/otp` — Completes sign-in after a valid login challenge has been created.
- `/register/verify-email` — Continues account email verification after registration.
- `/register/resend-email` — Resends an account-verification email during registration.
- `/verify-email` — Handles an email-verification link.
- `/reset-password` — Accepts a valid password-reset token and lets the user choose a new password.
- `/reset-password/success` — Password-reset confirmation page.
- `/register/success` — Registration confirmation page.

When giving a route, use a short Markdown link and explain in one sentence why the user should open it. Do not direct public users to any `/portal/admin/*` or `/admin/*` route.
