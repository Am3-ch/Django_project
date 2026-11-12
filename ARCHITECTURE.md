# System Architecture — MyMentor (django_blog)

This document describes the architecture of the project as it exists today: a server-rendered Django 5.2 monolith that provides user accounts (local + Google sign-in), user profiles, and a simple posts feed. It is deployed to Render (`mymentor-oped.onrender.com`) behind Gunicorn.

---

## 1. High-level overview

```
                         ┌──────────────────────────────┐
   Browser  ──HTTP──▶    │  Gunicorn (WSGI server)      │
                         │   └─ django_blog.wsgi        │
                         └──────────────┬───────────────┘
                                        │
                         ┌──────────────▼───────────────┐
                         │  Middleware stack            │
                         │  Security → WhiteNoise       │
                         │  → Session → Common → CSRF   │
                         │  → Auth → Messages           │
                         │  → Clickjacking → allauth    │
                         └──────────────┬───────────────┘
                                        │
                         ┌──────────────▼───────────────┐
                         │  URL router                  │
                         │  django_blog/urls.py         │
                         └──┬─────────┬──────────┬──────┘
                            │         │          │
                 ┌──────────▼──┐ ┌────▼─────┐ ┌──▼──────────────┐
                 │ users app   │ │ blog app │ │ django-allauth  │
                 │ (accounts,  │ │ (posts)  │ │ (Google OAuth)  │
                 │  profiles)  │ │          │ │                 │
                 └──────┬──────┘ └────┬─────┘ └──┬──────────────┘
                        │             │          │
                 ┌──────▼─────────────▼──────────▼──────┐
                 │  Django ORM  →  SQLite (db.sqlite3)  │
                 └──────────────────────────────────────┘
                        │
                 ┌──────▼───────────┐     ┌─────────────────────┐
                 │ media/ (uploads) │     │ staticfiles/ served │
                 │ profile_pics/    │     │ by WhiteNoise       │
                 └──────────────────┘     └─────────────────────┘

   External services: Google OAuth 2.0 (sign-in), Gmail SMTP (password reset e-mail),
                      jsDelivr CDN (Bootstrap 4 CSS)
```

---

## 2. Repository layout

```
Django_project/
├── README.md
├── ARCHITECTURE.md                  ← this file
└── django_blog/                     ← Django project root (manage.py lives here)
    ├── manage.py                    CLI entry point (runserver, migrate, collectstatic…)
    ├── requirements.txt             Python dependencies
    ├── db.sqlite3                   SQLite database
    ├── django_blog/                 Project configuration package
    │   ├── settings.py              Global configuration
    │   ├── urls.py                  Root URL routing
    │   ├── wsgi.py / asgi.py        Server entry points
    ├── blog/                        "Posts" feature app
    ├── users/                       Accounts & profiles app
    ├── static/                      Project-level static source files
    ├── staticfiles/                 collectstatic output (served by WhiteNoise)
    └── media/                       User-uploaded files (profile pictures, images)
```

---

## 3. Components and responsibilities

### 3.1 Project configuration — `django_blog/django_blog/`

| File | Responsibility |
|---|---|
| `settings.py` | Loads environment values (`.env` / host env vars via `django-environ`). Declares installed apps, middleware, templates, database, static/media paths, auth backends, allauth/Google provider config, crispy-forms pack, e-mail (SMTP) settings, login/logout redirects. |
| `urls.py` | Root router. Mounts the admin, the `blog` app under `/home/`, the `users` views, Django's built-in auth views (login, logout, password reset), and `allauth` under `/accounts/`. Serves `media/` when `DEBUG=True`. |
| `wsgi.py` | WSGI entry point used by Gunicorn in production. |
| `asgi.py` | ASGI entry point (unused today; available for async servers). |

### 3.2 `users` app — accounts and profiles

| File | Responsibility |
|---|---|
| `models.py` | `Profile` — one-to-one with Django's `User`; stores a profile `image` (default `default.jpg`, uploaded to `media/profile_pics/`). `save()` resizes images larger than 300×300 using Pillow. |
| `signals.py` | `post_save` receivers on `User`: automatically create a `Profile` when a user is created (including users created via Google sign-in) and save it whenever the user is saved. |
| `apps.py` | `UsersConfig.ready()` imports `signals` so the receivers are registered at startup. |
| `forms.py` | `UserRegisterForm` (username, email, password1/2), `UserUpdateForm` (username, email), `ProfileUpdateForm` (image). |
| `views.py` | `landing_page` (public entry page at `/`), `register` (local sign-up), `profile` (login-required; edits user + profile together). |
| `admin.py` | Registers `Profile` in the Django admin. |
| `templates/users/` | Landing, login, logout, register, profile and the three password-reset pages. All extend `blog/base.html`. |

### 3.3 `blog` app — posts

| File | Responsibility |
|---|---|
| `models.py` | `Post` — `title`, `content`, `date_posted`, `author` (FK → `User`, cascade delete). `get_absolute_url()` points to the detail page. |
| `views.py` | Class-based CRUD views: `PostListView` (home feed, login required, newest first), `PostDetailView`, `PostCreateView` (sets author to current user), `PostUpdateView` / `PostDeleteView` (only the author may edit/delete via `UserPassesTestMixin`). `about` function view. |
| `urls.py` | Routes under `/home/`: `''` (feed), `post/<pk>/`, `post/<pk>/update`, `post/<pk>/delete`, `post/new/`, `about/`. |
| `admin.py` | Registers `Post` in the Django admin. |
| `templates/blog/` | `base.html` (site shell: navbar "MyMentor", Bootstrap 4, messages, auth-aware links) plus home, detail, form and delete-confirm templates. |
| `static/blog/main.css` | Site stylesheet. |
| `static/blog/img/` | Site images used by the landing page (hero image, button icons). |

### 3.4 Authentication layer

Two parallel login paths share the same `User` table:

1. **Local accounts** — Django's `ModelBackend` with `LoginView`/`LogoutView` and the password-reset views (`/login/`, `/logout/`, `/password-reset/…`). Registration is the custom `users.views.register`.
2. **Google sign-in** — `django-allauth` (`allauth`, `allauth.account`, `allauth.socialaccount`, Google provider) via `allauth.account.auth_backends.AuthenticationBackend`. Mounted at `/accounts/`. `SOCIALACCOUNT_LOGIN_ON_GET = True` skips allauth's intermediate confirmation page; `prompt: select_account` forces Google's account chooser. Requires `django.contrib.sites` (`SITE_ID = 2`) and a `SocialApp` record (client ID/secret) configured in the admin. `PyJWT` + `cryptography` are needed by allauth to verify Google ID tokens.

Redirects: `LOGIN_URL = landing-page`, `LOGIN_REDIRECT_URL = blog-home`, `LOGOUT_REDIRECT_URL = blog-home`.

### 3.5 Presentation layer

- Server-rendered Django templates (`APP_DIRS = True`, no project-level template dir).
- Bootstrap 4 loaded from jsDelivr CDN; forms rendered with `django-crispy-forms` + `crispy-bootstrap4`.
- Flash messages via `django.contrib.messages`.

### 3.6 Data layer

- **Database:** SQLite file `db.sqlite3` via the Django ORM.
- **Core tables:** `auth_user`, `users_profile`, `blog_post`, plus allauth (`account_emailaddress`, `socialaccount_socialaccount`, `socialaccount_socialapp`, `socialaccount_socialtoken`), `django_site`, sessions, admin log.

```
User 1 ── 1 Profile
User 1 ── * Post
User 1 ── * SocialAccount (Google)
```

### 3.7 Static and media files

| Kind | Source | Served by |
|---|---|---|
| Static (CSS, site images, admin assets) | `blog/static/`, `static/` → collected into `staticfiles/` with `collectstatic`, compressed and hashed by WhiteNoise (`STORAGES['staticfiles']`) | WhiteNoise middleware (dev and prod) |
| Media (user uploads) | `media/` (`MEDIA_ROOT`) | Django only when `DEBUG=True`; nothing serves it in production |

### 3.8 External services

| Service | Used for |
|---|---|
| Google OAuth 2.0 | Social sign-in (scopes `profile`, `email`). |
| Gmail SMTP (`smtp.gmail.com`, TLS) | Sending password-reset e-mails. |
| jsDelivr CDN | Bootstrap 4 stylesheet. |
| Render | Hosting; runs the app with Gunicorn. |

---

## 4. Request flows

**Local login** — `GET /` → landing page → `/login/` → `LoginView` authenticates via `ModelBackend` → session created → redirect to `/home/` (`PostListView`).

**Google login** — landing page "Sign up with Google" → `/accounts/google/login/?next=/home` → redirect to Google → callback `/accounts/google/login/callback/` → allauth creates/links `User` + `SocialAccount` → `post_save` signal creates `Profile` → session created → redirect to `/home`.

**Create post** — `/home/post/new/` (login required) → `PostCreateView` sets `author = request.user` → saved → redirect to `get_absolute_url()` (detail page).

**Update profile** — `/profile/` → `UserUpdateForm` + `ProfileUpdateForm` validated together → image saved to `media/profile_pics/` and resized → redirect back to `/profile/`.

---

## 5. URL map

| Path | View | Auth |
|---|---|---|
| `/` | `users.landing_page` | public |
| `/register/` | `users.register` | public |
| `/login/`, `/logout/` | Django `LoginView` / `LogoutView` | public |
| `/password-reset/…` | Django password-reset views | public |
| `/profile/` | `users.profile` | login required |
| `/home/` | `PostListView` | login required |
| `/home/post/<pk>/` | `PostDetailView` | public |
| `/home/post/new/` | `PostCreateView` | login required |
| `/home/post/<pk>/update` | `PostUpdateView` | author only |
| `/home/post/<pk>/delete` | `PostDeleteView` | author only |
| `/home/about/` | `about` | public |
| `/accounts/…` | django-allauth | mixed |
| `/admin/` | Django admin | staff |

---

## 6. Known issues / technical debt

**Configuration:** secrets and environment-specific values (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`) are read with `django-environ` from `django_blog/.env` locally (git-ignored; see `.env.example`), or from the host's environment variables on Render.

**Database:** `DATABASES` is built from the `DATABASE_URL` environment variable (for example a Render Postgres URL). If it isn't set, the app uses the local `db.sqlite3`.

Still open (these need a decision or infrastructure outside the code):

- **Old `SECRET_KEY` is in git history:** a new key now lives in `.env`. Production needs its own key set on Render.
- **User uploads in production:** profile pictures are stored in `media/`, which isn't served when `DEBUG=False`. Render's filesystem is also wiped on each deploy, so uploads are lost. Object storage (S3, Cloudinary) is the usual fix.
- **SQLite on Render** is wiped on each deploy too. To switch to Postgres, create a Render Postgres database, set `DATABASE_URL`, add `psycopg[binary]` to `requirements.txt`, and run `migrate`. The Google `SocialApp` record and the `Site` (`SITE_ID = 2`) then need re-creating in the admin.
- **`db.sqlite3`, `media/` and `staticfiles/` are committed to git.** They're left tracked on purpose for now: production currently relies on the committed database (users, the Google `SocialApp`) and on `media/default.jpg`. Untrack them once Postgres and object storage are in place. Render can then run `collectstatic` at build time.
