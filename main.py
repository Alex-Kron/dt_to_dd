import requests
import os
from dotenv import load_dotenv
from requests import session
import datetime
from product_mapping import PRODUCTS_MAPPING
import aiohttp
import asyncio
import argparse

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


async def get_dt_projects(session, base_url: str, token: str) -> list:
    projects = []
    page_number = 1
    page_size = 10

    while True:
        url = f"{base_url}/api/v1/project?pageSize={page_size}&pageNumber={page_number}"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers)

        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                batch = await response.json()
                if not batch:
                    break
                projects.extend(batch)
                page_number += 1
            else:
                text = await response.text()
                raise Exception(f"Ошибка получения списка проектов: {response.status} - {text}")


    return projects


async def get_dd_engagements(session, base_url: str, token: str) -> set:
    url = f"{base_url}/api/v2/engagements/?limit=500"
    headers = {"Authorization": f"Token {token}"}
    async with session.get(url, headers=headers) as response:
        if response.status == 200:
            data = await response.json()
            return {engagement["name"]: engagement["id"] for engagement in data.get("results", [])}
        else:
            text = await response.text()
            raise Exception(f"Ошибка получения списка engagements: {response.status} - {text}")


async def create_dd_engagement(session, base_url: str, token: str, name: str):
    url = f"{base_url}/api/v2/engagements/"
    product_id = PRODUCTS_MAPPING.get(name, 3)
    if "candidate" in name:
        product_id = 3
    else:
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

    async with session.post(url, headers=headers, json=data) as response:
        if response.status not in [200,201]:
            text = await response.text()
            raise Exception(f"Ошибка создания engagement: {response.status} - {text}")


async def sync_projects_to_dd(session, dt_base_url: str, dt_token: str, dd_base_url: str, dd_token: str):
    dt_projects = await get_dt_projects(session, dt_base_url, dt_token)
    dd_engagements = await get_dd_engagements(session, dd_base_url, dd_token)

    dt_project_names = {project["name"] for project in dt_projects}
    dd_engagement_names = set(dd_engagements.keys())

    new_projects = dt_project_names - dd_engagement_names
    if new_projects:
        tasks = []
        for project in new_projects:
            task = asyncio.create_task(
                create_dd_engagement(session, dd_base_url, dd_token, project)
            )
            tasks.append(task)
        await asyncio.gather(*tasks)
    print(f"Добавлено {len(new_projects)} новых engagements в DefectDojo.")


async def download_fpf_file(session, base_url: str, token: str, project_id: str) -> bytes:
    url = f"{base_url}/api/v1/finding/project/{project_id}/export"
    headers = {"Authorization": f"Bearer {token}"}

    async with session.get(url, headers=headers) as response:
        if response.status != 200:
            text = await response.text()
            raise Exception(f"Ошибка скачивания FPF файла: {response.status} - {text}")
        return await response.read()

async def upload_scan_to_dd(session, base_url: str, token: str, engagement_id: int, scan_data: bytes, version: str):
    url = f"{base_url}/api/v2/import-scan/"
    headers = {
        "Authorization": f"Token {token}"
    }

    # Преобразуем данные в формат string($binary)
    data = {
        "engagement": str(engagement_id),
        "scan_type": "Dependency Track Finding Packaging Format (FPF) Export",
        "tags": "dependency-track",
        "test_title": version
    }

    form = aiohttp.FormData()
    form.add_field("file", scan_data, filename="scan.fpf", content_type="application/octet-stream")

    for key, value in data.items():
        form.add_field(key, value)

    async with session.post(url, headers=headers, data=form) as response:
        if response.status not in [200,201]:
            text = await response.text()
            raise Exception(f"Ошибка загрузки скана: {response.status_code} - {response.text}")


async def reimport_scan_to_dd(session, base_url: str, token: str, engagement_id: int, scan_data: bytes, test_id: int):
    url = f"{base_url}/api/v2/reimport-scan/"
    headers = {
        "Authorization": f"Token {token}"
    }

    # Преобразуем данные в формат string($binary)
    data = {
        "engagement": str(engagement_id),
        "scan_type": "Dependency Track Finding Packaging Format (FPF) Export",
        "tags": "dependency-track",
        "test": str(test_id)
    }

    form = aiohttp.FormData()
    form.add_field("file", scan_data, filename="scan.fpf", content_type="application/octet-stream")

    for key, value in data.items():
        form.add_field(key, value)

    async with session.post(url, headers=headers, data=form) as response:
        if response.status not in [200, 201]:
            text = await response.text()
            raise Exception(f"Ошибка загрузки скана: {response.status_code} - {response.text}")


async def get_tests_by_engagement_id(session, engagement_id: int, base_url: str, token: str):
    headers = {
        "Authorization": f"Token {token}",
    }
    url = f"{base_url}/api/v2/tests/"
    params = {"engagement": engagement_id}
    async with session.get(url, headers=headers, params=params) as response:
        if response.status == 200:
            data = await response.json()
            return data.get("results", [])
        else:
            text = await response.text()
            raise Exception(f"Ошибка получения тестов: {response.status} - {text}")

def test_exists_with_title(tests, test_title):
    return any(test["title"] == test_title for test in tests)

def test_get_id(tests, test_title):
    for test in tests:
        if test["title"] == test_title:
            return test["id"]

async def process_projects(session, dt_base_url: str, dt_token: str, dd_base_url: str, dd_token: str, reimport: bool):
    projects = await get_dt_projects(session, dt_base_url, dt_token)
    engagements = await get_dd_engagements(session, dd_base_url, dd_token)

    tasks = []

    for project in projects:
        project_name = project["name"]
        project_id = project["uuid"]
        project_version = project.get("version", "unknown")
        engagement_id = engagements.get(project_name)

        if not engagement_id:
            print(f"Engagement для {project_name} не найден")
            continue

        tests = await get_tests_by_engagement_id(session, engagement_id, dd_base_url, dd_token)
        test_exists = test_exists_with_title(tests, project_version)
        if test_exists:
            test_id = test_get_id(tests, project_version)
        task = asyncio.create_task(
            handle_project(session, dt_base_url, dd_base_url, dt_token, dd_token, project_id, project_name, engagement_id, project_version, test_exists, test_id, reimport)
        )
        tasks.append(task)
    await asyncio.gather(*tasks)

async def handle_project(session, dt_base_url, dd_base_url, dt_token, dd_token, project_id, project_name, engagement_id, project_version, test_exists, test_id, reimport):
    timestamp = datetime.datetime.now()
    if not test_exists:
        scan_data = await download_fpf_file(session, dt_base_url, dt_token, project_id)
        await upload_scan_to_dd(session, dd_base_url, dd_token, engagement_id, scan_data, project_version)
        print(f"{timestamp} [IMPORT] Проект {project_name}: добавлено сканирование - {project_version} (isTestExist: {test_exists}, test_id: {test_id})")
    elif reimport:
        scan_data = await download_fpf_file(session, dt_base_url, dt_token, project_id)
        await reimport_scan_to_dd(session, dd_base_url, dd_token, engagement_id, scan_data, test_id)
        print(f"{timestamp} [REIMPORT] Проект {project_name}: обновлено сканирование - {project_version} (isTestExist: {test_exists}, test_id: {test_id})")
    else:
        print(f"{timestamp} [WARNING] Проект {project_name}: реимпорт выключен - {project_version} (isTestExist: {test_exists}, test_id: {test_id})")

async def main():
    parser = argparse.ArgumentParser(description="Скрипт для работы с проектами Dependency-Track и DefectDojo.")
    parser.add_argument('--reimport', action='store_true', help='Включить реимпорт сканов, если они уже существуют')
    args = parser.parse_args()

    dt_token = get_dependency_track_token(DT_URL, DT_USERNAME, DT_PASSWORD)
    async with aiohttp.ClientSession() as session:
        await sync_projects_to_dd(session, DT_URL, dt_token, DD_URL, DD_TOKEN)
        await process_projects(session, DT_URL, dt_token, DD_URL, DD_TOKEN, args.reimport)


if __name__ == "__main__":
    asyncio.run(main())