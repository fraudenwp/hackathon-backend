# Dev env setup

Docker env setup:

```sh
# dev
docker compose -f docker-compose.dev.yml up --build -d
#prod
docker-compose up -d --build
# then visit http://localhost:8004 for api
```

(If you will work with docker, local env setup is not crucial.)
Local env setup:

```sh
cp .env.example .env

pip install pip-tools
pip-compile --no-emit-index-url requirements.dev.in
pip install -r requirements.dev.txt
docker compose -f docker-compose.dev.yml up --build -d
# then open vs code, clik Run and Debug, select Web: Remote Attach and start. This step for start backend server
docker-compose -f docker-compose.dev.yml exec web alembic upgrade head # for migrations

```

- recommended db visualizer : dbeaver

When you add a new package to requirements.in , please update `requirements.txt`:

```sh
pip-compile --no-emit-index-url
pip-compile --no-emit-index-url requirements.dev.in
```

> [!NOTE]
> When running first time, dont forget to apply the migration.

```sh
docker-compose -f docker-compose.dev.yml exec web alembic upgrade head
```

If you changed a db model, please run:

```sh
docker-compose -f docker-compose.dev.yml exec web alembic revision --autogenerate -m "REASON OF CHANGE"
# then apply the migration
docker-compose -f docker-compose.dev.yml exec web alembic upgrade head
# version history
docker-compose -f docker-compose.dev.yml exec web alembic history
# version heads
docker-compose -f docker-compose.dev.yml exec web alembic heads
# init migrations
docker-compose -f docker-compose.dev.yml exec web alembic init ./migrations

# merge migrations
docker-compose -f docker-compose.dev.yml exec web alembic merge -m "merge 197069afc347 and a5e723aabcf4" 197069afc347 a5e723aabcf4
```

# Linting

We are using `ruff`as a linter.

```sh
ruff check
ruff check --fix
ruff format
```

# Notifications

We use firebase to send push notifications.

FIREBASE_CONFIG

# Debug server

In vs code, - run docker-compose `docker compose -f docker-compose.dev.yml up --build` - go to run and debug, select "Web and Taskiq" and run
Horay, you can debug taskiq and web instances simultaneusly.

