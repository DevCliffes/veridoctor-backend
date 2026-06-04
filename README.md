# Veridoctor backend service

# Getting started

- python 3.12
- [Poetry](https://python-poetry.org/) for package mangement.
- Docker for containerization

1. Install dependencies

```sh
poetry install
```

2. Start the server

```sh
docker compose up -d
```

## Adding dependencies
Example: adding the requests package
```sh
poetry add requests
```
## running migrations
1. Generate the migration files
```sh
poetry run python manage.py makemigrations
```
2. Restart the docker container to apply the migrations
```sh
docker compose down && sudo docker compose up -d
```