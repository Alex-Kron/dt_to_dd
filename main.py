import requests
import os
from dotenv import load_dotenv
from datetime import datetime
from product_mapping import PRODUCTS_MAPPING
import argparse
import re

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
        return response.text.strip()
    else:
        raise Exception(f"Ошибка получения токена: {response.status_code} - {response.text}")

def get_dt_projects(base_url: str, token: str) -> list:
    projects = []
    page_number = 1
    page_size = 10
    sort_name = "version"
    sort_order = "asc"
    while True:
        url = f"{base_url}/api/v1/project?pageSize={page_size}&pageNumber={page_number}&sortName={sort_name}&sortOrder={sort_order}"
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

def get_dd_engagements(base_url: str, token: str) -> dict:
    url = f"{base_url}/api/v2/engagements/?limit=500"
    headers = {"Authorization": f"Token {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return {eng["name"]: eng["id"] for eng in data.get("results", [])}
    else:
        raise Exception(f"Ошибка получения списка engagements: {response.status_code} - {response.text}")

def create_dd_engagement(base_url: str, token: str, name: str):
    url = f"{base_url}/api/v2/engagements/"
    product_id = PRODUCTS_MAPPING.get(name, 3)
    if product_id is None:
        product_id = 1
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json"
    }
    data = {
        "tags": [],
        "name": name,
        "description": "Import from Dependency Track",
        "version": None,
        "first_contacted": None,
        "target_start": "2025-01-01",
        "target_end": "2030-01-01",
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
    for project in new_projects:
        create_dd_engagement(dd_base_url, dd_token, project)
    print(f"Добавлено {len(new_projects)} новых engagements в DefectDojo.")

def download_fpf_file(base_url: str, token: str, project_id: str) -> bytes:
    url = f"{base_url}/api/v1/finding/project/{project_id}/export"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Ошибка скачивания FPF файла: {response.status_code} - {response.text}")
    return response.content

def upload_scan_to_dd(base_url: str, token: str, engagement_id: int, scan_data: bytes, version: str, scan_date: str):
    url = f"{base_url}/api/v2/import-scan/"
    headers = {"Authorization": f"Token {token}"}
    num, tool = None, None
    if 'release/' in version:
        match = re.search(r'release/(\d+)-(.*)', version)
        if match:
            num = match.group(1)
            tool = match.group(2)

    data = {
        "scan_date": scan_date,
        "engagement": str(engagement_id),
        "scan_type": "Dependency Track Finding Packaging Format (FPF) Export",
        "tags": "dependency-track",
        "close_old_findings": "true",
        "test_title": str(version)
    }
    if num:
        data["version"] = num
    if tool:
        data["service"] = tool

    files = {"file": ("scan.fpf", scan_data, "application/octet-stream")}
    response = requests.post(url, headers=headers, data=data, files=files)
    if response.status_code not in [200, 201]:
        raise Exception(f"Ошибка загрузки скана: {response.status_code} - {response.text}")

def reimport_scan_to_dd(base_url: str, token: str, engagement_id: int, scan_data: bytes, test_id: int, scan_date: str):
    url = f"{base_url}/api/v2/reimport-scan/"
    headers = {"Authorization": f"Token {token}"}
    data = {
        "scan_date": scan_date,
        "engagement": str(engagement_id),
        "scan_type": "Dependency Track Finding Packaging Format (FPF) Export",
        "tags": "dependency-track",
        "close_old_findings": "true",
        "test": str(test_id)
    }
    files = {"file": ("scan.fpf", scan_data, "application/octet-stream")}
    response = requests.post(url, headers=headers, data=data, files=files)
    if response.status_code not in [200, 201]:
        raise Exception(f"Ошибка загрузки скана: {response.status_code} - {response.text}")

def get_tests_by_engagement_id(engagement_id: int, base_url: str, token: str):
    headers = {"Authorization": f"Token {token}"}
    url = f"{base_url}/api/v2/tests/"
    params = {"engagement": engagement_id}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get("results", [])
    else:
        raise Exception(f"Ошибка получения тестов: {response.status_code} - {response.text}")

def test_exists_with_title(tests, test_title):
    return any(test["title"] == test_title for test in tests)

def test_get_id(tests, test_title):
    for test in tests:
        if test["title"] == test_title:
            return test["id"]

def handle_project(dt_base_url, dd_base_url, dt_token, dd_token, project_id, project_name, engagement_id, project_version, test_exists, test_id, scan_date, reimport):
    timestamp = datetime.now()
    if not test_exists:
        scan_data = download_fpf_file(dt_base_url, dt_token, project_id)
        upload_scan_to_dd(dd_base_url, dd_token, engagement_id, scan_data, project_version, scan_date)
        print(f"{timestamp} [IMPORT] Проект {project_name}: добавлено сканирование: version - {project_version} | test_exits - {test_exists} | scan_date - {scan_date}")
    elif reimport:
        scan_data = download_fpf_file(dt_base_url, dt_token, project_id)
        reimport_scan_to_dd(dd_base_url, dd_token, engagement_id, scan_data, test_id, scan_date)
        print(f"{timestamp} [REIMPORT] Проект {project_name}: обновлено сканирование: version - {project_version} | test_exits - {test_exists} | scan_date - {scan_date}")
    else:
        print(f"{timestamp} [WARNING] Проект {project_name}: реимпорт выключен: version - {project_version} | test_exits - {test_exists} | scan_date - {scan_date}")

def process_projects(dt_base_url: str, dt_token: str, dd_base_url: str, dd_token: str, reimport: bool):
    projects = get_dt_projects(dt_base_url, dt_token)
    engagements = get_dd_engagements(dd_base_url, dd_token)

    for project in projects:
        name = project["name"]
        pid = project["uuid"]
        dt = datetime.fromtimestamp(int(project["lastBomImport"]) / 1000)
        project_date = dt.strftime('%Y-%m-%d')
        version = project.get("version", "unknown")
        engagement_id = engagements.get(name)
        if not engagement_id:
            print(f"Engagement для {name} не найден")
            continue

        tests = get_tests_by_engagement_id(engagement_id, dd_base_url, dd_token)
        exists = test_exists_with_title(tests, version)
        tid = test_get_id(tests, version) if exists else -1
        handle_project(dt_base_url, dd_base_url, dt_token, dd_token, pid, name, engagement_id, version, exists, tid, project_date, reimport)

def main():
    parser = argparse.ArgumentParser(description="Скрипт для работы с проектами Dependency-Track и DefectDojo.")
    parser.add_argument('--reimport', action='store_true', help='Включить реимпорт сканов, если они уже существуют')
    args = parser.parse_args()

    dt_token = get_dependency_track_token(DT_URL, DT_USERNAME, DT_PASSWORD)
    sync_projects_to_dd(DT_URL, dt_token, DD_URL, DD_TOKEN)
    process_projects(DT_URL, dt_token, DD_URL, DD_TOKEN, args.reimport)

if __name__ == "__main__":
    main()
