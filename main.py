import requests
import os
from dotenv import load_dotenv

load_dotenv()

DT_URL = os.getenv('DT_URL')
DD_URL = os.getenv('DD_URL')
DT_USERNAME = os.getenv('DT_USERNAME')
DT_PASSWORD = os.getenv('DD_PASSWORD')
DD_TOKEN = os.getenv('DD_TOKEN')

def get_dependency_track_token(base_url: str, username: str, password: str) -> str:
    url = f"{base_url}/v1/user/login"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {"username": username, "password": password}

    response = requests.post(url, headers=headers, data=data)

    if response.status_code == 200:
        return response.text.strip()  # Token приходит в text/plain
    else:
        raise Exception(f"Ошибка получения токена: {response.status_code} - {response.text}")


def get_dt_projects(base_url: str, token: str) -> set:
    url = f"{base_url}/v1/project"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        projects = response.json()
        return {project["name"] for project in projects}
    else:
        raise Exception(f"Ошибка получения списка проектов: {response.status_code} - {response.text}")


def get_dd_engagements(base_url: str, token: str) -> set:
    url = f"{base_url}/api/v2/engagements/"
    headers = {"Authorization": f"Token {token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        engagements = response.json()["results"]
        return {engagement["name"] for engagement in engagements}
    else:
        raise Exception(f"Ошибка получения списка engagements: {response.status_code} - {response.text}")


def create_dd_engagement(base_url: str, token: str, name: str):
    url = f"{base_url}/api/v2/engagements/"
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": name,
        "status": "In Progress",
        "target_start": "2025-01-01",
        "target_end": "2025-12-31",
        "engagement_type": "CI/CD"
    }
    response = requests.post(url, headers=headers, json=data)

    if response.status_code not in [200, 201]:
        raise Exception(f"Ошибка создания engagement: {response.status_code} - {response.text}")


def sync_projects_to_dd(dt_base_url: str, dt_token: str, dd_base_url: str, dd_token: str):
    dt_projects = get_dt_projects(dt_base_url, dt_token)
    dd_engagements = get_dd_engagements(dd_base_url, dd_token)

    new_projects = dt_projects - dd_engagements
    for project in new_projects:
        create_dd_engagement(dd_base_url, dd_token, project)

    print(f"Добавлено {len(new_projects)} новых engagements в DefectDojo.")


def main():
    pass

if __name__ == "__main__":
    main()