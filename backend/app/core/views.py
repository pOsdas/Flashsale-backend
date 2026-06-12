from django.conf import settings
from django.http import HttpResponse, JsonResponse


def home_view(request):
    links = [
        {
            "title": "Admin",
            "url": "/api/v1/admin/",
        },
        {
            "title": "GraphQL",
            "url": "/api/v1/graphql/",
        },
    ]

    if settings.DEBUG:
        links.extend(
            [
                {
                    "title": "ReDoc",
                    "url": "/api/v1/redoc/",
                },
                {
                    "title": "Scalar Docs",
                    "url": "/api/v1/scalar-docs/",
                },
                {
                    "title": "Swagger UI",
                    "url": "/api/v1/docs/",
                },
                {
                    "title": "OpenAPI Schema",
                    "url": "/api/v1/schema/",
                },
            ]
        )

    links_html = "\n".join(
        f"""
        <a class="link-card" href="{link["url"]}">
            <span class="link-main">
                <span class="link-title">{link["title"]}</span>
                <span class="link-url">{link["url"]}</span>
            </span>
            <span class="arrow">→</span>
        </a>
        """
        for link in links
    )

    docs_notice = ""

    if not settings.DEBUG:
        docs_notice = """
        <div class="notice">
            API documentation is disabled because the application is running with <code>DEBUG=False</code>.
        </div>
        """

    html = f"""
    <!doctype html>
    <html lang="ru">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Flashsale Backend API</title>

        <style>
            :root {{
                --bg: #0f172a;
                --card-bg: #1e293b;
                --card-border: #334155;
                --text: #e5e7eb;
                --muted: #94a3b8;
                --title: #f8fafc;
                --accent: #8b5cf6;
                --accent-hover: #a78bfa;
                --link-bg: #111827;
                --link-border: #475569;
                --success: #22c55e;
                --warning-bg: rgba(251, 191, 36, 0.12);
                --warning-border: rgba(251, 191, 36, 0.32);
                --warning-text: #fde68a;
            }}

            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                min-height: 100vh;
                font-family: Arial, sans-serif;
                background:
                    radial-gradient(circle at top, rgba(139, 92, 246, 0.24), transparent 36%),
                    radial-gradient(circle at bottom right, rgba(34, 197, 94, 0.12), transparent 32%),
                    var(--bg);
                color: var(--text);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 32px 16px;
            }}

            .page {{
                width: 100%;
                max-width: 860px;
            }}

            .card {{
                background: rgba(30, 41, 59, 0.96);
                border: 1px solid var(--card-border);
                border-radius: 28px;
                padding: 36px;
                box-shadow: 0 28px 80px rgba(0, 0, 0, 0.38);
                backdrop-filter: blur(10px);
            }}

            .header {{
                margin-bottom: 30px;
                text-align: center;
            }}

            .badge {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 7px 13px;
                border-radius: 999px;
                background: rgba(34, 197, 94, 0.14);
                color: #bbf7d0;
                border: 1px solid rgba(34, 197, 94, 0.28);
                font-size: 14px;
                font-weight: 700;
                margin-bottom: 16px;
            }}

            .badge-dot {{
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--success);
                box-shadow: 0 0 14px rgba(34, 197, 94, 0.9);
            }}

            h1 {{
                margin: 0 0 12px;
                color: var(--title);
                font-size: 38px;
                line-height: 1.12;
                letter-spacing: -0.04em;
            }}

            p {{
                max-width: 620px;
                margin: 0 auto;
                color: var(--muted);
                line-height: 1.65;
                font-size: 16px;
            }}

            .grid {{
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 14px;
                margin-top: 28px;
            }}

            .link-card {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 18px;
                min-height: 88px;
                padding: 18px 20px;
                border-radius: 18px;
                background: var(--link-bg);
                border: 1px solid var(--link-border);
                text-decoration: none;
                color: var(--text);
                transition:
                    transform 0.15s ease,
                    border-color 0.15s ease,
                    background 0.15s ease,
                    box-shadow 0.15s ease;
            }}

            .link-card:hover {{
                transform: translateY(-2px);
                border-color: var(--accent);
                background: #172033;
                box-shadow: 0 12px 30px rgba(0, 0, 0, 0.22);
            }}

            .link-main {{
                display: flex;
                flex-direction: column;
                gap: 6px;
                min-width: 0;
            }}

            .link-title {{
                color: var(--title);
                font-size: 16px;
                font-weight: 800;
            }}

            .link-url {{
                color: var(--muted);
                font-size: 13px;
                overflow-wrap: anywhere;
            }}

            .arrow {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 34px;
                height: 34px;
                border-radius: 50%;
                background: rgba(139, 92, 246, 0.14);
                color: var(--accent-hover);
                font-size: 20px;
                flex-shrink: 0;
                transition:
                    background 0.15s ease,
                    color 0.15s ease;
            }}

            .link-card:hover .arrow {{
                background: rgba(139, 92, 246, 0.24);
                color: #ffffff;
            }}

            .notice {{
                margin-top: 26px;
                padding: 14px 16px;
                border-radius: 14px;
                background: var(--warning-bg);
                border: 1px solid var(--warning-border);
                color: var(--warning-text);
                font-size: 14px;
                line-height: 1.5;
                text-align: center;
            }}

            .footer {{
                margin-top: 28px;
                padding-top: 22px;
                border-top: 1px solid var(--card-border);
                color: var(--muted);
                font-size: 14px;
                text-align: center;
            }}

            code {{
                color: #ddd6fe;
                background: rgba(139, 92, 246, 0.12);
                padding: 3px 7px;
                border-radius: 7px;
            }}

            @media (max-width: 720px) {{
                body {{
                    align-items: flex-start;
                }}

                .card {{
                    padding: 24px;
                    border-radius: 22px;
                }}

                h1 {{
                    font-size: 30px;
                }}

                .grid {{
                    grid-template-columns: 1fr;
                }}

                .link-card {{
                    min-height: 78px;
                }}
            }}
        </style>
    </head>

    <body>
        <main class="page">
            <section class="card">
                <div class="header">
                    <div class="badge">
                        <span class="badge-dot"></span>
                        Flashsale Backend is running
                    </div>

                    <h1>Flashsale API</h1>

                    <p>
                        Main entry points for API administration, schema exploration
                        and service access.
                    </p>
                </div>

                <div class="grid">
                    {links_html}
                </div>

                {docs_notice}

                <div class="footer">
                    Static files route: <code>/static/</code>
                </div>
            </section>
        </main>
    </body>
    </html>
    """

    return HttpResponse(html)


def page_not_found_view(request, exception=None):
    if request.path.startswith("/api/") and _wants_json(request):
        return JsonResponse(
            {
                "detail": "Page not found.",
                "path": request.path,
                "available": _get_available_api_links(),
            },
            status=404,
        )

    docs_links_html = ""

    if settings.DEBUG:
        docs_links_html = """
        <div class="links">
            <a class="doc-link" href="/api/v1/docs/">Swagger UI</a>
            <a class="doc-link" href="/api/v1/redoc/">ReDoc</a>
            <a class="doc-link" href="/api/v1/scalar-docs/">Scalar Docs</a>
            <a class="doc-link" href="/api/v1/schema/">OpenAPI Schema</a>
        </div>
        """

    html = f"""
    <!doctype html>
    <html lang="ru">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Page Not Found — Flashsale API</title>

        <style>
            :root {{
                --bg: #0f172a;
                --card-bg: #1e293b;
                --card-border: #334155;
                --text: #e5e7eb;
                --muted: #94a3b8;
                --title: #f8fafc;
                --accent: #8b5cf6;
                --accent-hover: #a78bfa;
                --link-bg: #111827;
                --link-border: #475569;
                --danger: #fb7185;
            }}

            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                min-height: 100vh;
                font-family: Arial, sans-serif;
                background:
                    radial-gradient(circle at top, rgba(251, 113, 133, 0.18), transparent 34%),
                    radial-gradient(circle at bottom right, rgba(139, 92, 246, 0.14), transparent 34%),
                    var(--bg);
                color: var(--text);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 32px 16px;
            }}

            .page {{
                width: 100%;
                max-width: 760px;
            }}

            .card {{
                background: rgba(30, 41, 59, 0.96);
                border: 1px solid var(--card-border);
                border-radius: 28px;
                padding: 38px;
                box-shadow: 0 28px 80px rgba(0, 0, 0, 0.38);
                text-align: center;
            }}

            .code {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 92px;
                height: 92px;
                margin-bottom: 22px;
                border-radius: 26px;
                background: rgba(251, 113, 133, 0.12);
                color: #fecdd3;
                border: 1px solid rgba(251, 113, 133, 0.28);
                font-size: 34px;
                font-weight: 900;
            }}

            h1 {{
                margin: 0 0 12px;
                color: var(--title);
                font-size: 36px;
                line-height: 1.15;
                letter-spacing: -0.04em;
            }}

            p {{
                max-width: 620px;
                margin: 0 auto;
                color: var(--muted);
                line-height: 1.65;
                font-size: 16px;
            }}

            .path {{
                margin: 22px auto 0;
                max-width: 620px;
                padding: 13px 16px;
                border-radius: 14px;
                background: #111827;
                border: 1px solid #475569;
                color: #ddd6fe;
                font-family: Consolas, Monaco, monospace;
                font-size: 14px;
                overflow-wrap: anywhere;
                text-align: left;
            }}

            .actions {{
                display: flex;
                justify-content: center;
                gap: 12px;
                flex-wrap: wrap;
                margin-top: 28px;
            }}

            .button {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-height: 46px;
                padding: 0 18px;
                border-radius: 999px;
                text-decoration: none;
                color: #ffffff;
                background: var(--accent);
                font-weight: 800;
                transition:
                    background 0.15s ease,
                    transform 0.15s ease,
                    box-shadow 0.15s ease;
            }}

            .button:hover {{
                background: var(--accent-hover);
                transform: translateY(-1px);
                box-shadow: 0 12px 28px rgba(139, 92, 246, 0.22);
            }}

            .button.secondary {{
                background: var(--link-bg);
                border: 1px solid var(--link-border);
                color: var(--text);
            }}

            .button.secondary:hover {{
                background: #172033;
                box-shadow: none;
            }}

            .links {{
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 10px;
                margin-top: 26px;
            }}

            .doc-link {{
                padding: 13px 14px;
                border-radius: 14px;
                background: var(--link-bg);
                border: 1px solid var(--link-border);
                color: var(--text);
                text-decoration: none;
                font-size: 14px;
                font-weight: 700;
                transition:
                    transform 0.15s ease,
                    border-color 0.15s ease,
                    background 0.15s ease;
            }}

            .doc-link:hover {{
                transform: translateY(-1px);
                border-color: var(--accent);
                background: #172033;
            }}

            @media (max-width: 720px) {{
                body {{
                    align-items: flex-start;
                }}

                .card {{
                    padding: 26px;
                    border-radius: 22px;
                }}

                h1 {{
                    font-size: 30px;
                }}

                .links {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>

    <body>
        <main class="page">
            <section class="card">
                <div class="code">404</div>

                <h1>Page not found</h1>

                <p>
                    The requested page does not exist in Flashsale Backend API.
                    Check the address or return to the API home page.
                </p>

                <div class="path">
                    Requested path: {request.path}
                </div>

                <div class="actions">
                    <a class="button" href="/">Go to API home</a>
                    <a class="button secondary" href="/api/v1/admin/">Open Admin</a>
                </div>

                {docs_links_html}
            </section>
        </main>
    </body>
    </html>
    """

    return HttpResponse(html, status=404)


def _wants_json(request):
    accept = request.headers.get("Accept", "")

    return (
        "application/json" in accept
        or request.path.startswith("/api/v1/")
    )


def _get_available_api_links():
    links = {
        "admin": "/api/v1/admin/",
        "graphql": "/api/v1/graphql/",
    }

    if settings.DEBUG:
        links.update(
            {
                "redoc": "/api/v1/redoc/",
                "scalar": "/api/v1/scalar-docs/",
                "swagger": "/api/v1/docs/",
                "schema": "/api/v1/schema/",
            }
        )

    return links
