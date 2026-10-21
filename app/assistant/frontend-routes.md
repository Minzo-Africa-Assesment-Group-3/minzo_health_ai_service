# Available Minzo frontend routes

Use only the routes in this catalogue when directing a user to a Minzo page.
Do not invent routes or claim that a page exists when it is not listed here.

- `/` — Home page. Introduces the Minzo healthcare directory and its purpose.
- `/account-type` — Start account registration. The user chooses whether to register as an individual or as a business.
- `/register/user` — Individual account registration. For people who want to search, review, and follow businesses.
- `/register/business` — Business account registration. For an owner or manager registering a healthcare business.
- `/login` — Sign in to an existing Minzo account.
- `/forgot-password` — Start password recovery for an existing account.

## Flow-only routes

These pages are part of a process and should not normally be given as a starting link:

- `/otp` — Completes sign-in after a valid login challenge has been created.
- `/register/verify-email` — Continues account email verification after registration.
- `/verify-email` — Handles an email-verification link.
- `/register/success` — Registration confirmation page.

When giving a route, use a short Markdown link and explain in one sentence why the user should open it.
