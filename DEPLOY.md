# Deploy

This project can be deployed as a single web service because Flask now serves the built React frontend from `ui/dist`.

## Easiest Option: Render or Railway

1. Push the latest code to GitHub.
2. Create a new web service from the repo.
3. Let the platform build using the included `Dockerfile`.
4. Add environment variable:

```text
OPENAI_API_KEY=your_key_here
```

5. Deploy.

The service exposes one public URL that serves:

- the React UI at `/`
- the API at `/api/*`

## Local Docker Run

```bash
docker build -t riverline-assessment .
docker run -p 5000:5000 -e OPENAI_API_KEY=your_key_here riverline-assessment
```

Then open:

```text
http://localhost:5000
```
