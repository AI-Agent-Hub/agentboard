# -*- coding: utf-8 -*-
# @Time    : 2024/06/27

import codecs
import time
import uuid
import inspect
import re

def read_file(file_path):
    lines = []
    with codecs.open(file_path, "r", "utf-8") as file:
        lines = file.readlines()
    return lines

def save_file(file_path, lines):
    with codecs.open(file_path, "w", "utf-8") as file:
        for line in lines:
            file.write(line + "\n")
    file.close()

def get_current_timestamp():
    timestamp = int(time.time())
    return timestamp

def get_current_timestamp_milli():
    timestamp = round(time.time() * 1000)
    return timestamp

def get_current_datetime():
    import datetime    
    now = datetime.datetime.now()
    datetime = now.strftime('%Y-%m-%d %H:%M:%S')
    return datetime


def get_workflow_id():
    """
        Generate a random UUID as workflow id
    """
    workflow_id = str(uuid.uuid4())
    return workflow_id


def normalize_data_name(name):
    """
        normalize the input name to lower cases and concate with underscore "_"
    """
    name_lower = name.lower()
    words = name_lower.split(" ")
    name_normalize = "_".join(words)
    return name_normalize

### Agent Function Conversion
def function_to_schema(func) -> dict:
    """
        OpenAI Style function calling schema
    """
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }

    try:
        signature = inspect.signature(func)
    except ValueError as e:
        raise ValueError(
            f"Failed to get signature for function {func.__name__}: {str(e)}"
        )

    parameters = {}
    for param in signature.parameters.values():
        try:
            param_type = type_map.get(param.annotation, "string")
        except KeyError as e:
            raise KeyError(
                f"Unknown type annotation {param.annotation} for parameter {param.name}: {str(e)}"
            )
        parameters[param.name] = {"type": param_type}

    required = [
        param.name
        for param in signature.parameters.values()
        if param.default == inspect._empty
    ]

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": (func.__doc__ or "").strip(),
            "parameters": {
                "type": "object",
                "properties": parameters,
                "required": required,
            },
        },
    }


def function_to_schema_claude(func) -> dict:
    """
        Compatible with Claude's function calling schema
        Ref: 
        https://docs.anthropic.com/en/docs/build-with-claude/tool-use
    """
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }

    try:
        signature = inspect.signature(func)
    except ValueError as e:
        raise ValueError(
            f"Failed to get signature for function {func.__name__}: {str(e)}"
        )

    parameters = {}
    for param in signature.parameters.values():
        try:
            param_type = type_map.get(param.annotation, "string")
        except KeyError as e:
            raise KeyError(
                f"Unknown type annotation {param.annotation} for parameter {param.name}: {str(e)}"
            )
        parameters[param.name] = {"type": param_type}

    required = [
        param.name
        for param in signature.parameters.values()
        if param.default == inspect._empty
    ]

    return {
        "name" : func.__name__, 
        "description": (func.__doc__ or "").strip(),
        "input_schema": {
            "type": "object",
            "properties": parameters,
            "required": required
        }
    }


### MultiLinguistic Support 
def segment_text(text):
    """
        Segment input text to segment (english word, non-english chars) for highlight purpose

        text = 'This is a $dollar sign !!' ->  ['this', 'is', 'a', 'dollar', 'sign']
        text = '你好World什么是RAG' -> ['world', 'rag', '你', '好', '什', '么', '是']
        text = 'नमस्ते, दुनिया!' -> ['न', 'म', 'स', '्', 'त', 'े', ',', 'द', 'ु', 'न', 'ि', 'य', 'ा', '!']
    """
    segment_list = []
    text_norm = text.lower()
    sep = r"(\s+)"
    text_split = re.split(sep, text_norm)
    for split in text_split:
        if split.strip() == "":
            segment_list.append(split)
            continue
        if is_chinese_character(split):
            # extract all english segments
            alpha_num_seg = extract_alpha_numeric(split)
            zh_seg = extract_chinese_character(split)
            segment_list.extend(alpha_num_seg)
            segment_list.extend(zh_seg)
        ## ascii english and 
        elif is_english_character(split):
            alpha_num_seg = extract_alpha_numeric(split)
            segment_list.extend(alpha_num_seg)
        ## other language characters
        else:
            ## non ascii segment, just append the list of chars
            segment_list.extend(list(split))
    return segment_list

def is_chinese_character(text):
    """ Check if input text contains Chinese Characters
    """
    pattern = re.compile(r'[\u4e00-\u9fff]')
    return bool(pattern.search(text))


def is_english_character(text):
    """ Check if input text only contains english charaters
    """
    for char in text:
        if not (char.isascii()):
            return False
    return True

def extract_alpha_numeric(text):
    """
        text = 'This is a $dollar sign !!'
        text = '你好World什么是RAG'
        text = नमस्ते, दुनिया!
    """
    regex = r"[a-zA-Z0-9]+"
    matches = re.findall(regex, text)
    return matches

def extract_chinese_character(text):
    regex = r'[\u4e00-\u9fff]'
    matches = re.findall(regex, text)
    return matches

def is_character_alpha_numeric(text):
    """ Check if input charater contains only character and numeric 
    """
    for char in text:
        if not (char.isascii() and (char.isalnum() or char.isspace())):
            return False
    return True

def query_doc_highlight(query, doc, highlight_class):
    """
        query = "what's RAG and what's the difference bewteen RAG and LLM?"
        doc = "RAG is a term related to retrieval augumented generation using large language models(LLM)"

        Todo: keep original () and query upper case
    """
    query_segment = segment_text(query)
    doc_segment = segment_text(doc)

    query_seg_set = set()
    for seg in query_segment:
        if seg.strip() != "":
            query_seg_set.add(seg)

    doc_html = []
    highlight_mark = '<a class="{}">{}</a>'
    for seg in doc_segment:
        if seg.strip() == "":
            # keep original blank for readability
            doc_html.append(seg)
            continue
        if seg in query_seg_set:
            seg_highlight = highlight_mark.format(highlight_class, seg)
            doc_html.append(seg_highlight)
        else:
            doc_html.append(seg)
    doc_highlight = "".join(doc_html)
    return doc_highlight
