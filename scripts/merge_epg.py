#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并 EPG 文件：
 - 合并 channel，按 display-name 去重并补充缺少的名称
 - 每个 <channel> 标签后紧跟属于它的 <programme>
 - 后续文件新增 channel id 在基底文件最大 id 基础上累加
 - 美化输出 XML
"""

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from xml.dom import minidom
import re

# 合并任务定义
MERGES = [
    ("epg/1d.xml", ["epg/e.xml", "epg/plsy1_1d.xml", "epg/112114.xml"]),
    ("epg/7d.xml", ["epg/all.xml", "epg/plsy1_7d.xml"]),
]

def parse_tree(path: str):
    if not os.path.exists(path):
        print(f"⚠️ 文件不存在: {path}")
        return None
    try:
        return ET.parse(path)
    except Exception as e:
        print(f"⚠️ 解析失败 {path}: {e}")
        return None

def get_all_names(ch: ET.Element) -> set[str]:
    return {dn.text.strip() for dn in ch.findall("display-name") if dn.text}

def clean_text(s: str) -> str:
    if not s:
        return s
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', s)

def remove_whitespace_nodes(elem):
    for child in list(elem):
        if child.text:
            child.text = clean_text(child.text.strip())
        if child.tail:
            child.tail = clean_text(child.tail.strip())
        remove_whitespace_nodes(child)

def prettify_xml(elem: ET.Element) -> bytes:
    remove_whitespace_nodes(elem)
    rough_string = ET.tostring(elem, encoding='utf-8').decode('utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ", encoding="utf-8", newl="\n")

def merge_files(output_file: str, input_files: list[str]):
    print(f"▶️ 合并: {input_files} -> {output_file}")

    base_tree = None
    base_root = None
    name_map = {}        # display-name -> channel element
    id_map = {}          # 原 id -> 新 id
    max_id = 0
    programmes_map = {}  # 新 id -> programme 列表

    for idx, f in enumerate(input_files):
        tree = parse_tree(f)
        if tree is None:
            continue
        root = tree.getroot()

        if idx == 0:
            base_tree = tree
            base_root = root
            # 修改 <tv> 属性
            base_root.set("generator-info-name", "tvsilo.vip")
            base_root.set("generator-info-url", "https://github.com/g12777/TV")

            # 增加 date 属性，为当前系统时间 +8 时区
            tz_utc8 = timezone(timedelta(hours=8))
            now_utc8 = datetime.now(tz_utc8)
            date_str = now_utc8.strftime("%Y%m%d%H%M%S")
            base_root.set("date", date_str)

            for ch in base_root.findall("channel"):
                cid = ch.get("id")
                if not cid:
                    continue
                for n in get_all_names(ch):
                    name_map[n] = ch
                try:
                    max_id = max(max_id, int(cid))
                except ValueError:
                    pass
                programmes_map[cid] = []

            # 收集 programme 并移除
            for p in base_root.findall("programme"):
                ch_id = p.get("channel")
                if ch_id in programmes_map:
                    programmes_map[ch_id].append(p)
            for p in base_root.findall("programme"):
                base_root.remove(p)
            continue

        # 合并频道
        for ch in root.findall("channel"):
            ch_names = get_all_names(ch)
            if not ch_names:
                continue
            old_id = ch.get("id")

            target_ch = None
            for n in ch_names:
                if n in name_map:
                    target_ch = name_map[n]
                    break

            if target_ch is not None:
                # 已存在频道合并 display-name
                existing_names = get_all_names(target_ch)
                for n in ch_names:
                    if n not in existing_names:
                        new_dn = ET.Element("display-name")
                        new_dn.text = n
                        target_ch.append(new_dn)
                        name_map[n] = target_ch
                new_id = target_ch.get("id")
            else:
                # 新增频道，id 连续累加
                max_id += 1
                new_id = str(max_id)
                ch.set("id", new_id)
                base_root.append(ch)
                for n in ch_names:
                    name_map[n] = ch
                programmes_map[new_id] = []

            # 用原 id 映射到新 id
            id_map[old_id] = new_id

        # 合并 programme
        for p in root.findall("programme"):
            old_ch_id = p.get("channel")
            new_ch_id = id_map.get(old_ch_id)
            if not new_ch_id:
                print(f"⚠️ 找不到对应频道：{old_ch_id}")
                continue
            p.set("channel", new_ch_id)
            if new_ch_id not in programmes_map:
                programmes_map[new_ch_id] = []
            programmes_map[new_ch_id].append(p)

    # 调整顺序：每个 <channel> 后紧跟属于它的 <programme>
    # 先移除所有 programme
    for p in base_root.findall("programme"):
        base_root.remove(p)

    # 再按频道顺序插回
    for ch in base_root.findall("channel"):
        cid = ch.get("id")
        insert_pos = list(base_root).index(ch) + 1
        for p in programmes_map.get(cid, []):
            base_root.insert(insert_pos, p)
            insert_pos += 1

    # 写出美化 XML
    if base_tree is not None:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        ET.indent(base_tree, space="  ")
        base_tree.write(output_file, encoding="utf-8", xml_declaration=True)
        print(f"✅ 合并完成 -> {output_file}")
    else:
        print(f"⚠️ 未生成文件: {output_file}")

def main():
    for out_file, ins in MERGES:
        merge_files(out_file, ins)

if __name__ == "__main__":
    main()
