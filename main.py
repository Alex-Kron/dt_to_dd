import requests
import os
from dotenv import load_dotenv
from product_mapping import PRODUCTS_MAPPING

load_dotenv()

DT_URL = os.getenv('DT_URL')
DD_URL = os.getenv('DD_URL')
DT_USERNAME = os.getenv('DT_USERNAME')
DT_PASSWORD = os.getenv('DT_PASSWORD')
DD_TOKEN = os.getenv('DD_TOKEN')

def get_dependency_track_token(base_url: str, username: str, password: str) -> str:
    url = f"{base_url}/api/v1/user/login"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {"username": username, "password": password}

    response = requests.post(url, headers=headers, data=data)

    if response.status_code == 200:
        return response.text.strip()  # Token приходит в text/plain
    else:
        raise Exception(f"Ошибка получения токена: {response.status_code} - {response.text}")


def get_dt_projects(base_url: str, token: str) -> list:
    projects = []
    page_number = 1
    page_size = 10

    while True:
        url = f"{base_url}/api/v1/project?pageSize={page_size}&pageNumber={page_number}"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            batch = response.json()
            if not batch:
                break
            projects.extend(batch)
            page_number += 1
        else:
            raise Exception(f"Ошибка получения списка проектов: {response.status_code} - {response.text}")

    return projects


def get_dd_engagements(base_url: str, token: str) -> set:
    url = f"{base_url}/api/v2/engagements/?limit=500"
    headers = {"Authorization": f"Token {token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        engagements = response.json()["results"]
        return {engagement["name"]:engagement["id"] for engagement in engagements}
    else:
        raise Exception(f"Ошибка получения списка engagements: {response.status_code} - {response.text}")


def create_dd_engagement(base_url: str, token: str, name: str):
    url = f"{base_url}/api/v2/engagements/"
    product_id = PRODUCTS_MAPPING.get(name, 3)
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json"
    }
    data = {
        "tags": ["Dependency Track"],
        "name": name,
        "description": "Import from Dependency Track",
        "version": None,
        "first_contacted": None,
        "target_start": "2025-04-01",
        "target_end": "2030-04-01",
        "reason": None,
        "tracker": None,
        "test_strategy": "",
        "threat_model": False,
        "api_test": False,
        "pen_test": False,
        "check_list": False,
        "status": "In Progress",
        "engagement_type": "CI/CD",
        "build_id": None,
        "commit_hash": None,
        "branch_tag": None,
        "source_code_management_uri": None,
        "deduplication_on_engagement": True,
        "lead": 1,
        "requester": None,
        "preset": None,
        "report_type": None,
        "product": product_id,
        "build_server": None,
        "source_code_management_server": None,
        "orchestration_engine": None
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code not in [200, 201]:
        raise Exception(f"Ошибка создания engagement: {response.status_code} - {response.text}")


def sync_projects_to_dd(dt_base_url: str, dt_token: str, dd_base_url: str, dd_token: str):
    dt_projects = get_dt_projects(dt_base_url, dt_token)
    dd_engagements = get_dd_engagements(dd_base_url, dd_token)

    dt_project_names = {project["name"] for project in dt_projects}
    dd_engagement_names = set(dd_engagements.keys())

    new_projects = dt_project_names - dd_engagement_names
    if len(new_projects) > 0:
        for project in new_projects:
            create_dd_engagement(dd_base_url, dd_token, project)

    print(f"Добавлено {len(new_projects)} новых engagements в DefectDojo.")


def download_fpf_file(base_url: str, token: str, project_id: str) -> bytes:
    url = f"{base_url}/api/v1/finding/project/{project_id}/export"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.content
    else:
        raise Exception(f"Ошибка скачивания FPF файла: {response.status_code} - {response.text}")


def upload_scan_to_dd(base_url: str, token: str, engagement_id: int, scan_data: bytes, version: str):
    url = f"{base_url}/api/v2/import-scan/"
    headers = {
        "Authorization": f"Token {token}"
    }

    # Преобразуем данные в формат string($binary)
    data = {
        "engagement": str(engagement_id),
        "scan_type": "Dependency Track Finding Packaging Format (FPF) Export",
        "tags": version
    }

    # Отправляем файл как бинарные данные
    files = {
        "file": ("scan.fpf", scan_data)
    }

    response = requests.post(url, headers=headers, files=files, data=data)

    if response.status_code not in [200, 201]:
        raise Exception(f"Ошибка загрузки скана: {response.status_code} - {response.text}")


def process_projects(dt_base_url: str, dt_token: str, dd_base_url: str, dd_token: str):
    projects = get_dt_projects(dt_base_url, dt_token)
    engagements = get_dd_engagements(dd_base_url, dd_token)

    for project in projects:
        project_name = project["name"]
        project_id = project["uuid"]
        project_version = project.get("version", "unknown")

        engagement_id = engagements.get(project_name)
        if engagement_id:
            scan_data = download_fpf_file(dt_base_url, dt_token, project_id)
            upload_scan_to_dd(dd_base_url, dd_token, engagement_id, scan_data, project_version)
            print(f"Загружен FPF файл для {project_name} (версия {project_version}) в engagement {engagement_id}")
        else:
            print(f"Engagement для {project_name} не найден в DefectDojo")


def main():
    dt_token = get_dependency_track_token(DT_URL, DT_USERNAME, DT_PASSWORD)
    sync_projects_to_dd(DT_URL, dt_token, DD_URL, DD_TOKEN)
    process_projects(DT_URL, dt_token, DD_URL, DD_TOKEN)

if __name__ == "__main__":
    main()