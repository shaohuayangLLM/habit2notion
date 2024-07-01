#!/usr/bin/python
# -*- coding: UTF-8 -*-
import argparse
import json
import os
import time

import pendulum
from notion_helper import NotionHelper, TAG_ICON_URL
import mistletoe
from notion_helper import NotionHelper
from notion_renderer import NotionPyRenderer
import requests
import utils
from dotenv import load_dotenv

load_dotenv()

habit_icon_dict = {
    "habit_exercising":"https://www.notion.so/icons/gym_gray.svg",
    "habit_drink_water":"https://www.notion.so/icons/drink_gray.svg"
}


def get_token(client_id, client_secret, code, redirect_uri):
    url = "https://api.ticktick.com/oauth/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "scope": "tasks:write tasks:read",
    }
    response = requests.post(url, data=data)

    if response.status_code == 200:
        token = response.json()["access_token"]
        return token
    else:
        print("Error occurred:", response.text)
        return None


def get_user_projects(access_token):
    url = "https://api.ticktick.com/open/v1/project"
    headers = {"Authorization": "Bearer " + access_token}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        projects = response.json()
        return projects
    else:
        print("Error occurred:", response.text)
        return None


headers = {
    "authority": "api.dida365.com",
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9",
    "cache-control": "no-cache",
    "content-type": "application/json;charset=UTF-8",
    "hl": "zh_CN",
    "origin": "https://dida365.com",
    "pragma": "no-cache",
    "referer": "https://dida365.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "x-tz": "Asia/Shanghai",
}


def is_task_modified(item):
    id = item.get("id")
    if item.get("modifiedTime") is None:
        return True
    modified_time = utils.parse_date(item.get("modifiedTime"))
    todo = todo_dict.get(id)
    if todo:
        last_modified_time = utils.get_property_value(
            todo.get("properties").get("最后修改时间")
        )
        if last_modified_time == modified_time:
            return False
    return True


def is_tomato_modified(item):
    id = item.get("id")
    tomato = tomato_dict.get(id)
    if tomato:
        task_id = utils.get_property_value(tomato.get("properties").get("任务id"))
        note = utils.get_property_value(tomato.get("properties").get("笔记"))
        if task_id == item.get("task_id") and note == item.get("note"):
            return False
    return True


def is_habit_modified(item):
    id = item.get("id")
    modified_time = utils.parse_date(item.get("modifiedTime"))
    habit = habit_dict.get(id)
    if habit:
        last_modified_time = utils.get_property_value(
            habit.get("properties").get("最后修改时间")
        )
        if last_modified_time == modified_time:
            return False
    return True


def is_habit_records_modified(item):
    id = item.get("id")
    modified_time = utils.parse_date(item.get("opTime"))
    habit_record = habit_record_dict.get(id)
    if habit_record:
        last_modified_time = utils.get_property_value(
            habit_record.get("properties").get("最后修改时间")
        )
        if last_modified_time == modified_time:
            return False
    return True


def is_project_modified(item):
    id = item.get("id")
    if item.get("modifiedTime") is None:
        return True
    modified_time = utils.parse_date(item.get("modifiedTime"))
    project = project_dict.get(id)
    if project:
        last_modified_time = utils.get_property_value(
            project.get("properties").get("最后修改时间")
        )
        if last_modified_time == modified_time:
            return False
    return True


def get_projects():
    """获取所有清单"""
    r = requests.get("https://api.dida365.com/api/v2/projects", headers=headers)
    if r.ok:
        # 获取映射关系
        d = notion_helper.get_property_type(notion_helper.project_database_id)
        items = r.json()
        items = list(filter(is_project_modified, items))
        for item in items:
            emoji, title = utils.split_emoji_from_string(item.get("name"))
            id = item.get("id")
            project = {
                "标题": title,
                "id": id,
                "最后修改时间": utils.parse_date(item.get("modifiedTime")),
            }
            icon = {"type": "emoji", "emoji": emoji}
            properties = utils.get_properties(project, d)
            if id in project_dict:
                notion_helper.update_page(
                    page_id=project_dict.get(id).get("id"),
                    properties=properties,
                    icon=icon,
                )
            else:
                parent = {
                    "database_id": notion_helper.project_database_id,
                    "type": "database_id",
                }
                result = notion_helper.create_page(
                    parent=parent, properties=properties, icon=icon
                )
                project_dict[id] = result
    else:
        print(f" Get projects failed ${r.text}")


def remove_duplicates(data):
    seen_ids = set()
    unique_data = []
    for item in data:
        if item["id"] not in seen_ids:
            unique_data.append(item)
            seen_ids.add(item["id"])
    return unique_data


def get_pomodoros():
    result = []
    to = None
    while True:
        url = "https://api.dida365.com/api/v2/pomodoros/timeline"
        if to:
            url += f"?to={to}"
        r = requests.get(
            url=url,
            headers=headers,
        )
        if r.ok:
            l = r.json()
            if len(l) == 0:
                break
            result.extend(l)
            completedTime = l[-1].get("startTime")
            to = pendulum.parse(completedTime).int_timestamp * 1000

        else:
            print(f"获取任务失败 {r.text}")
    results = remove_duplicates(result)
    # 处理result
    for result in results:
        if result.get("tasks"):
            tasks = [
                item
                for item in result.get("tasks")
                if item.get("taskId") and item.get("title")
            ]
            if len(tasks):
                result["title"] = tasks[0].get("title")
                result["task_id"] = tasks[0].get("taskId")
    return results


def get_habits():
    url = "https://api.dida365.com/api/v2/habits"
    r = requests.get(
        url=url,
        headers=headers,
    )
    if r.ok:
        return r.json()


def get_habit_records():
    """习惯记录"""
    data = {
        "habitIds": ["6672585af67d91037bde232c"],
        "afterStamp": 20240320,
    }
    r = requests.post(
        "https://api.dida365.com/api/v2/habitCheckins/query", headers=headers, json=data
    )
    if r.ok:
        return r.json().get("checkins").get("6672585af67d91037bde232c")


def insert_habit_records():
    d = notion_helper.get_property_type(notion_helper.habit_record_database_id)
    items = get_habit_records()
    if items:
        items = list(filter(is_habit_records_modified, items))
        for index, item in enumerate(items):
            print(f"一共{len(items)}个，当前是第{index+1}个")
            id = item.get("id")
            habit_id = item.get("habitId")
            habit_name = utils.get_property_value(
                habit_dict.get(habit_id).get("properties").get("标题")
            )
            habit_re_id = habit_dict.get(habit_id).get("id")
            habit = {
                "标题": habit_name,
                "id": id,
                "最后修改时间": utils.parse_date(item.get("opTime")),
                "日期": utils.parse_date(str(item.get("checkinStamp"))),
                "目标": item.get("goal"),
                "值": item.get("value"),
                "习惯": [habit_re_id],
            }
            parent = {
                "database_id": notion_helper.habit_record_database_id,
                "type": "database_id",
            }
            if item.get("checkinTime"):
                habit["完成时间"] = utils.parse_date(item.get("checkinTime"))
            properties = utils.get_properties(habit, d)
            parent = {
                "database_id": notion_helper.habit_record_database_id,
                "type": "database_id",
            }
            icon = habit_dict.get(habit_id).get("icon")
            if id in habit_record_dict:
                notion_helper.update_page(
                    page_id=habit_record_dict.get(id).get("id"),
                    properties=properties,
                    icon=icon,
                )
            else:
                notion_helper.create_page(
                    parent=parent, properties=properties, icon=icon
                )


def insert_habits():
    d = notion_helper.get_property_type(notion_helper.habit_database_id)
    items = get_habits()
    if items:
        items = list(filter(is_habit_modified, items))
        for index, item in enumerate(items):
            print(f"一共{len(items)}个，当前是第{index+1}个")
            print(item.get("targetDays"))
            id = item.get("id")
            habit = {
                "标题": item.get("name"),
                "id": id,
                "最后修改时间": utils.parse_date(item.get("modifiedTime")),
                "单位": item.get("unit"),
                "目标": item.get("goal"),
                "目标天数": item.get("targetDays"),
                "提示语": item.get("encouragement"),
            }
            properties = utils.get_properties(habit, d)
            parent = {
                "database_id": notion_helper.habit_database_id,
                "type": "database_id",
            }
            icon = habit_icon_dict.get(item.get("iconRes"))
            if icon is None:
                icon = "https://www.notion.so/icons/alarm_clock_gray.svg"
            if id in habit_dict:
                notion_helper.update_page(
                    page_id=habit_dict.get(id).get("id"),
                    properties=properties,
                    icon=habit_dict.get(id).get("icon"),
                )
            else:
                result = notion_helper.create_page(
                    parent=parent, properties=properties, icon=utils.get_icon(icon),
                )
                habit_dict[id] = result


def insert_tamato():
    d = notion_helper.get_property_type(notion_helper.tomato_database_id)
    items = get_pomodoros()
    items = list(filter(is_tomato_modified, items))
    for index, item in enumerate(items):
        print(f"一共{len(items)}个，当前是第{index+1}个")
        id = item.get("id")
        tomato = {
            "标题": item.get("title"),
            "id": id,
            "开始时间": utils.parse_date(item.get("startTime")),
            "结束时间": utils.parse_date(item.get("endTime")),
        }
        if item.get("note"):
            tomato["笔记"] = item.get("note")
        if item.get("task_id") and item.get("task_id") in todo_dict:
            tomato["任务"] = [todo_dict.get(item.get("task_id")).get("id")]
        if item.get("task_id") and item.get("task_id"):
            tomato["任务id"] = item.get("task_id")
        properties = utils.get_properties(tomato, d)
        notion_helper.get_date_relation(properties, pendulum.parse(item.get("endTime")))
        parent = {
            "database_id": notion_helper.tomato_database_id,
            "type": "database_id",
        }
        icon = {"type": "emoji", "emoji": "🍅"}
        if id in tomato_dict:
            notion_helper.update_page(
                page_id=tomato_dict.get(id).get("id"),
                properties=properties,
                icon=icon,
            )
        else:
            notion_helper.create_page(parent=parent, properties=properties, icon=icon)


def get_all_completed():
    """获取所有完成的任务"""
    date = pendulum.now()
    result = []
    while True:
        to = date.format("YYYY-MM-DD HH:mm:ss")
        r = requests.get(
            f"https://api.dida365.com/api/v2/project/all/completedInAll/?from=&to={to}&limit=100",
            headers=headers,
        )
        if r.ok:
            l = r.json()
            result.extend(l)
            completedTime = l[-1].get("completedTime")
            date = pendulum.parse(completedTime)
            if len(l) < 100:
                break
        else:
            print(f"获取任务失败 {r.text}")
    result = remove_duplicates(result)
    return result


def get_all_task():
    """获取所有未完成的任务"""
    r = requests.get("https://api.dida365.com/api/v2/batch/check/0", headers=headers)
    results = []
    if r.ok:
        results.extend(r.json().get("syncTaskBean").get("update"))
    else:
        print(f"获取任务失败 {r.text}")
    return results


def get_task():
    """获取所有清单"""
    results = get_all_completed()
    results.extend(get_all_task())
    add_task_to_notion(results)


def add_task_to_notion(items, page_id=None):
    d = notion_helper.get_property_type(notion_helper.todo_database_id)
    items = list(filter(is_task_modified, items))
    for index, item in enumerate(items):
        id = item.get("id")
        task = {"标题": item.get("title"), "id": id, "状态": "Not started"}
        if page_id:
            task["Parent task"] = [page_id]
        if item.get("projectId") and item.get("projectId") in project_dict:
            task["清单"] = [project_dict.get(item.get("projectId")).get("id")]
        if item.get("startDate"):
            task["开始时间"] = utils.parse_date(item.get("startDate"))
            task["time"] = item.get("startDate")
        if item.get("dueDate"):
            task["结束时间"] = utils.parse_date(item.get("dueDate"))
        if item.get("modifiedTime"):
            task["最后修改时间"] = utils.parse_date(item.get("modifiedTime"))
        if item.get("progress"):
            task["进度"] = item.get("progress") / 100
        if item.get("tags"):
            task["标签"] = [
                notion_helper.get_relation_id(
                    x, notion_helper.tag_database_id, TAG_ICON_URL
                )
                for x in item.get("tags")
            ]
        parent = {
            "database_id": notion_helper.todo_database_id,
            "type": "database_id",
        }
        icon = "https://www.notion.so/icons/circle_outline_green.svg"
        properties = utils.get_properties(task, d)
        if item.get("completedTime"):
            task["状态"] = "Done"
            task["完成时间"] = utils.parse_date(item.get("completedTime"))
            task["time"] = item.get("completedTime")
            icon = "https://www.notion.so/icons/checkmark_circle_green.svg"
            properties = utils.get_properties(task, d)
        notion_helper.get_all_relation(properties)
        if task.get("time"):
            notion_helper.get_date_relation(
                properties, pendulum.parse(task.get("time"))
            )
        if id in todo_dict:
            result = notion_helper.update_page(
                page_id=todo_dict.get(id).get("id"),
                properties=properties,
                icon=utils.get_icon(icon),
            )
        else:
            result = notion_helper.create_page(
                parent=parent, properties=properties, icon=utils.get_icon(icon)
            )
            todo_dict[id] = result
        if item.get("content"):
            add_content(result.get("id"), item.get("content"))
        if item.get("items"):
            add_task_to_notion(item.get("items"), result.get("id"))


def add_content(page_id, content):
    blocks = mistletoe.markdown(content, NotionPyRenderer)
    append_block(page_id, blocks)

def append_block(block_id, blocks):
    for block in blocks:
        children = None
        if block.get("children"):
            children = block.pop("children")
        id = notion_helper.client.blocks.children.append(block_id=block_id, children=[block]).get("results")[0].get("id")
        if children:
            append_block(id,children)


if __name__ == "__main__":
    headers["cookie"] = os.getenv("COOKIE")
    notion_helper = NotionHelper()
    projects = notion_helper.query_all(notion_helper.project_database_id)
    project_dict = {}
    for item in projects:
        project_dict[utils.get_property_value(item.get("properties").get("id"))] = item
    get_projects()
    todos = notion_helper.query_all(notion_helper.todo_database_id)
    todo_dict = {}
    for todo in todos:
        todo_dict[utils.get_property_value(todo.get("properties").get("id"))] = todo
    get_task()
    tomatos = notion_helper.query_all(notion_helper.tomato_database_id)
    tomato_dict = {}
    for tomato in tomatos:
        tomato_dict[utils.get_property_value(tomato.get("properties").get("id"))] = tomato
    insert_tamato()
    habits = notion_helper.query_all(notion_helper.habit_database_id)
    habit_dict = {}
    for habit in habits:
        habit_dict[utils.get_property_value(habit.get("properties").get("id"))] = habit
    insert_habits()
    habit_records = notion_helper.query_all(notion_helper.habit_record_database_id)
    habit_record_dict = {}
    for record in habit_records:
        habit_record_dict[
            utils.get_property_value(record.get("properties").get("id"))
        ] = record
    insert_habit_records()
