# AutomaWeb Frontend

Lightweight SPA frontend served directly by FastAPI.

## Stack

- Vanilla JavaScript with ES Modules
- Axios for API requests
- ToastifyJS for notifications
- Vitest for unit tests

## Run

```bash
cd frontend
npm install
cd ..
poetry run python dev.py
```

App URL: `http://localhost:8888`

## Test

```bash
cd frontend
npm run test
```

## Frontend Architecture

Note: FastAPI currently serves static files from `frontend/public`, so the architecture is placed there.

```
frontend/
    package.json
    public/
        index.html
        app.js
        router.js
        api/
            client.js
            automaweb.api.js
            test/
                automaweb.api.spec.js
        services/
            test.service.js
            scan.service.js
        components/
            button.js
            modal.js
            toast.js
            loader.js
        pages/
            dashboard/
                dashboard.page.js
                dashboard.html
            test-generator/
                generator.page.js
                generator.html
            project-scan/
                scan.page.js
                scan.html
        state/
            store.js
        utils/
            dom.js
            validators.js
            helpers.js
            test/
                utils.spec.js
        styles/
            global.css
            layout.css
            components.css
```

## Folder Responsibilities

- `api/`: only low-level HTTP communication and endpoint mapping.
- `services/`: business rules, validation, and orchestration of API calls.
- `components/`: reusable UI blocks without page-specific rules.
- `pages/`: route-level screens; light orchestration and event binding.
- `state/`: centralized app state with subscribe/update pattern.
- `utils/`: pure reusable helpers and DOM utilities.
- `styles/`: global tokens, layout system, and component-level styles.
- `test/`: unit tests colocated by domain using the `*.spec.js` pattern.
