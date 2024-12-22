# -*- coding: utf-8 -*-

import os
import time
import threading
import queue
import traceback
from flask import Flask, jsonify, request, render_template, g
import codecs
import json
import argparse

from .core_constants import *
from .db.db_sqllite import insert_db_sql, query_db, get_db
from .utils import query_doc_highlight

####### Global variables
user_input_logdir = DEFAULT_LOG_DIR
user_input_static_dir = DEFAULT_STATIC_DIR
user_input_db_dir = DEFAULT_DB_DIR
# Create a queue to store incoming requests
counter = 0
request_queue = queue.Queue()

#### Constants
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
## SET Flask DATABASE parameters default path to /python/site_packages/db/xxx.db
current_directory = os.path.dirname(os.path.abspath(__file__))
default_db_path = os.path.normpath(os.path.join(current_directory, DEFAULT_DB_DIR, DEFAULT_DB_FILE_SQLITE))
app.config['DATABASE'] = default_db_path
app.config['STATIC_FOLDER'] = STATIC_FOLDER_PATH
app.config['TEMPLATE_FOLDER'] = TEMPLATE_FOLDER_PATH

### AGENTBOARD SIDEBAR TAB LIST
BOARD_TYPE_LIST = [DATA_TYPE_TEXT, DATA_TYPE_DICT, DATA_TYPE_TOOL, DATA_TYPE_IMAGE, DATA_TYPE_AUDIO
    , DATA_TYPE_VIDEO, DATA_TYPE_MESSAGES, DATA_TYPE_RAG]

# Function to process the queue
def process_queue():
    global counter
    while True:
        if not request_queue.empty():
            # Process the request (example: increase counter)
            request = request_queue.get()
            counter += 1
            print(f"Request processed. Counter: {counter}")
        time.sleep(1)  # Add delay to prevent busy-waiting

def get_latest_file(folder_path):
    """
        only log file with format filename.log can be treated as valid log files
    """
    filename_list = []
    for filename in os.listdir(folder_path):
        # only support file_name,ext format
        pairs = filename.split(".")
        if len(pairs) != 2:
            print ("DEBUG: get_latest_file Input Log filename %s invalid and skipped" % filename)
            continue
        if pairs[1] != LOG_FILE_EXT_LOG:
            continue
        timestamp = 0
        try:
            timestamp = int(pairs[0])
        except Exception as e:
            print ("DEBUG: get_latest_file input file name not in timestamp int format %s" % pairs[0])
            timestamp = 0
        filename_list.append((timestamp, filename))
    if len(filename_list) == 0:
        return None
    filename_list_sorted = sorted(filename_list, key=lambda x:x[0], reverse=True)
    filename_latest = filename_list_sorted[0][1] if len(filename_list_sorted[0]) == 2 else None
    return filename_latest

def get_log_file(folder_path, logfile):
    """
        if user define a log file name and folder, and file exists, use the file,
        otherwise, use the files with the latest timestamp
    """
    if logfile is not None and os.path.exists(os.path.join(folder_path, logfile)):
        # current logfile exists, priority 1 use user defined file
        return logfile
    return get_latest_file(folder_path)

def get_db_file(db_dir, db_file):
    """ Get Agentboard Default DB File
    """
    # default path ./site_packages/agentboard/db/sqllite_database.db
    current_directory = os.path.dirname(os.path.abspath(__file__))
    default_db_path = os.path.normpath(os.path.join(current_directory, DEFAULT_DB_DIR, DEFAULT_DB_FILE_SQLITE))
    print ("DEBUG: AgentBoard Installed Default DB File Path %s" % default_db_path)

    if db_dir is None or db_file is None:
        print ("DEBUG: Agentboard Input db_dir %s|db_file %s|using default db_path %s" % (str(db_dir), str(db_file), str(default_db_path)))
        return default_db_path
    db_path = os.path.join(db_dir, db_file)
    if os.path.exists(db_path):
        print ("DEBUG: Agentboard Input DB|db_dir %s|db_file %s|using final db_path %s" % (str(db_dir), str(db_file), str(db_path)))
        return db_path
    else:
        print ("DEBUG: Agentboard Input DB|db_dir %s|db_file %s|Input DB File Path %s Doesn't Exist|Setting default db path %s" % (str(db_dir), str(db_file), str(db_path), str(default_db_path)))
        return default_db_path

def process_log_dir(logdir, default_dir):
    """
        input dir can be both relative and absolute dir
        if logdir is None, set to default package installation path
        otherwise: set to user defined path, no matter the static path is absoluate or relative
        
        Case: 
            ./log
            ./ext_log
    """
    print ("DEBUG: Agentboard Python Entry file logdir %s, default_dir %s" % (logdir, default_dir))
    # priorirt 1: user defined
    if (logdir is not None and logdir != "") and os.path.exists(logdir):
        # only return current logdir when logdir is not None and logdir exists.
        return logdir
    # priorirt 2: check default dir e.g. ./log ./static
    if os.path.exists(default_dir):
        return default_dir
    # priorirt 3: check package installation default dir e.g. ${install_path}/log ${install_path}/static
    # default file path and default folder
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # concate current_dir->default_dir and remove unnecessary .
    final_dir = os.path.abspath(os.path.join(current_dir, default_dir))
    return final_dir

def process_static_dir(static, default_static_dir):
    """
        input dir can be both relative and absolute dir
        if logdir is None, set to default package installation path
        otherwise: set to user defined path, no matter the static path is absoluate or relative
    """
    print ("DEBUG: Agentboard Python Entry file logdir %s, default_dir %s" % (static, default_static_dir))
    # priorirt 1: user defined
    if static is not None and static != "":
        return static
    # priorirt 2: check default dir e.g. ./log ./static
    if os.path.exists(default_static_dir):
        return default_static_dir
    # priorirt 3: check package installation default dir e.g. ${install_path}/log ${install_path}/static
    # default file path and default folder
    current_dir = os.path.dirname(os.path.abspath(__file__))
    final_dir = os.path.join(current_dir, default_static_dir)
    return final_dir

def agentboard_log_main():
    """
        display agentboard log main page
    """
    logdata_list = []
    type_list = []
    datatype_group = {}
    try:
        global user_input_logdir
        global user_input_logfile
        ## process logdir and support relative and absolute path
        logdir = process_log_dir(user_input_logdir, DEFAULT_LOG_DIR)
        print ("DEBUG: Main AgentBard Log Dir is %s, user_input_logdir is %s" % (str(logdir), str(user_input_logdir)))

        latest_filename = get_log_file(logdir, user_input_logfile)
        print ("DEBUG: Main AgentBard user_input_logfile is %s, final log_file choosen is %s" % (str(user_input_logfile), str(latest_filename)))

        if latest_filename is None:
            print ("DEBUG: get_agentboard return empty valid log files from path %s" % logdir)
            return 

        latest_filepath = os.path.join(logdir, latest_filename)
        print ("DEBUG: AgentBoard Loading logs from path %s" % latest_filepath)

        # read file utf-8
        log_dict_list = [] 
        agent_log_dict = {}   # KV, K1: agent_name, K2: list
        data_type_set = set()        
        with codecs.open(latest_filepath, 'r', encoding='utf-8') as file:
            # Read all contents of the file
            for line in file:
                line = line.strip()
                try:
                    line_json = json.loads(line)
                    cur_agent_name = line_json["agent_name"] if "agent_name" in line_json else ""
                    cur_data_type = line_json["data_type"] if "data_type" in line_json else ""
                    data_type_set.add(cur_data_type)

                    ## RAG group by result for display
                    if cur_data_type == DATA_TYPE_RAG:
                        line_json = rag_data_display_row_mapper(line_json)

                    if cur_agent_name in agent_log_dict:
                        log_dict_list = agent_log_dict[cur_agent_name]
                        log_dict_list.append(line_json)
                        agent_log_dict[cur_agent_name] = log_dict_list
                    else:
                        agent_log_dict[cur_agent_name] = [line_json]
                except Exception as e:
                    print ("ERROR: Processing log line data %s" % line)
                    s = traceback.format_exc()
                    print (s)
        
        ## visualize the log_dict_list, split by type
        datatype_group = {} # KKV, K1: agent_name, K2: group(image/audio), V: list of data
        for agent_name, log_dict_list in agent_log_dict.items():
            cur_agent_dict = {}
            for log_dict in log_dict_list:
                datatype = log_dict[KEY_DATA_TYPE] if KEY_DATA_TYPE in log_dict else None
                # agent loop and workflow can't be displayed on the main page. Without correct template /workflow.html
                if datatype is None or datatype in [DATA_TYPE_AGENT_LOOP, DATA_TYPE_WORKFLOW]:
                    continue 
                if datatype in cur_agent_dict:
                    cur_list = cur_agent_dict[datatype]
                    cur_list.append(log_dict)
                    cur_agent_dict[datatype] = cur_list
                else:
                    cur_agent_dict[datatype] = [log_dict]
            datatype_group[agent_name] = cur_agent_dict

        ## filter
        # type_list = list(data_type_set)
        type_list = BOARD_TYPE_LIST
        ## DEBUG: default set first data_type
        # datatype_list = datatype_group[type_list[0]] if len(type_list) > 0 else []
    except Exception as e:
        print (e)
    return render_template('agentboard_main.html', data = datatype_group, types = type_list)

@app.route('/web_static/<path:filename>')
def web_static_file(filename):
    """ serve web static folder, different from others
    """
    global user_input_static_dir
    agentboard_defined_static = user_input_static_dir
    return send_from_directory(agentboard_defined_static, filename)

@app.route('/', methods=['GET'])
def get_agentboard():
    """
    """
    return agentboard_log_main()

@app.route('/log', methods=['GET'])
def get_agentboard_log():
    """
    """
    return agentboard_log_main()

def rag_data_display_row_mapper(input_dict):
    """
        Display Rag Data Row Mapper
        input: dict
        input["data"]["input"]["query"] list of query
        input["data"]["output"]["docs"]  list of json dict
        input["data"]"output"]["key_doc_id"]  str, key of doc_id
        input["data"]"output"]["key_doc_content"] strm key of doc_content
        input["data"]"output"]["key_doc_embedding"] strm key of embedding

        # Required:
            queury
            embedding

            doc_id
            score
            content
            ext_info
    """
    ## group by result for display
    query_list = input_dict["data"]["input"]["query"]

    docs = input_dict["data"]["output"]["docs"]
    key_doc_id = input_dict["data"]["output"][KEY_DOC_ID]
    key_doc_content = input_dict["data"]["output"][KEY_DOC_CONTENT]
    key_doc_embedding = input_dict["data"]["output"][KEY_DOC_EMBEDDING]
    key_doc_score = input_dict["data"]["output"][KEY_DOC_SCORE]

    data_display = []
    for query, doc_list in zip(query_list, docs):
        query_text = query["query"]
        query_embedding = query["embedding"]
        query_embedding_display = query["embedding_display"]
        ## map doc key to standard
        doc_list_mapped = []
        for doc in doc_list:
            # required fields
            if DEFAULT_KEY_DOC_ID not in doc:
                doc[DEFAULT_KEY_DOC_ID] = (doc[key_doc_id] if key_doc_id in doc else "")
            if DEFAULT_KEY_DOC_CONTENT not in doc:
                doc[DEFAULT_KEY_DOC_CONTENT] = (doc[key_doc_content] if key_doc_content in doc else "")
            if DEFAULT_KEY_DOC_EMBEDDING not in doc:
                doc[DEFAULT_KEY_DOC_EMBEDDING] = (doc[key_doc_embedding] if key_doc_embedding in doc else "")
            if DEFAULT_KEY_DOC_SCORE not in doc:
                score = doc[key_doc_score] if key_doc_score in doc else 0.0
                doc[DEFAULT_KEY_DOC_SCORE] = DATA_FORMAT_DEFAULT_SCORE_FORMAT.format(score)
            else:
                score = doc[DEFAULT_KEY_DOC_SCORE]
                doc[DEFAULT_KEY_DOC_SCORE] = DATA_FORMAT_DEFAULT_SCORE_FORMAT.format(score)
            ## highlight html
            doc_text = doc["content"]
            doc[DEFAULT_KEY_DOC_CONTENT_HIGHLIGHT] = query_doc_highlight(query_text, doc_text, "div_a_highlight")
            doc_list_mapped.append(doc)
        data_display.append((query, doc_list_mapped))
    input_dict[KEY_DATA_DISPLAY] = data_display
    return input_dict

@app.route('/log/<data_type>', methods=['GET'])
def get_agentboard_datatype(data_type):
    """
    """
    logdata_list = []
    type_list = []
    try:
        global user_input_logdir
        global user_input_logfile
        ## process logdir and support relative and absolute path
        logdir = process_log_dir(user_input_logdir, DEFAULT_LOG_DIR)
        latest_filename = get_log_file(logdir, user_input_logfile)
        print ("DEBUG: Main AgentBard Log Dir is %s, logfile is %s" % (str(logdir), str(latest_filename)))

        if latest_filename is None:
            print ("DEBUG: get_agentboard return empty logs from path %s" % logdir)
            return 
        latest_filepath = os.path.join(logdir, latest_filename)
        print ("DEBUG: AgentBoard Loading logs from path %s" % latest_filepath)

        # read file utf-8
        log_dict_list = [] 
        agent_log_dict = {}   # KV, K1: agent_name, K2: list
        data_type_set = set()        
        with codecs.open(latest_filepath, 'r', encoding='utf-8') as file:
            # Read all contents of the file
            for line in file:
                line = line.strip()
                try:
                    line_json = json.loads(line)
                    cur_agent_name = line_json["agent_name"] if "agent_name" in line_json else ""
                    cur_data_type = line_json["data_type"] if "data_type" in line_json else ""
                    data_type_set.add(cur_data_type)


                    # only filter the required data_type
                    if cur_data_type != data_type:
                        continue
                    ## group by result for display
                    if data_type == DATA_TYPE_RAG:
                        line_json = rag_data_display_row_mapper(line_json)

                    if cur_agent_name in agent_log_dict:
                        log_dict_list = agent_log_dict[cur_agent_name]
                        log_dict_list.append(line_json)
                        agent_log_dict[cur_agent_name] = log_dict_list
                    else:
                        agent_log_dict[cur_agent_name] = [line_json]
                except Exception as e:
                    print (e)
        ## visualize the log_dict_list, split by type
        datatype_group = {} # KKV, K1: agent_name, K2: group(image/audio), V: list of data
        for agent_name, log_dict_list in agent_log_dict.items():
            cur_agent_dict = {}
            for log_dict in log_dict_list:
                datatype = log_dict[KEY_DATA_TYPE] if KEY_DATA_TYPE in log_dict else None
                if datatype is  None:
                    continue 
                if datatype in cur_agent_dict:
                    cur_list = cur_agent_dict[datatype]
                    cur_list.append(log_dict)
                    cur_agent_dict[datatype] = cur_list
                else:
                    cur_agent_dict[datatype] = [log_dict]
            datatype_group[agent_name] = cur_agent_dict

        ## filter
        # type_list = list(data_type_set)
        type_list = BOARD_TYPE_LIST

        ## DEBUG: default set first data_type
        # datatype_list = datatype_group[type_list[0]] if len(type_list) > 0 else []
    except Exception as e:
        print (e)
    return render_template('agentboard_main.html', data = datatype_group, types = type_list)


@app.route('/log/workflow', methods=['GET'])
def get_agent_workflow():
    """
    """
    logdata_list = []
    type_list = BOARD_TYPE_LIST
    workflow_dict = {}
    try:
        global user_input_logdir
        global user_input_logfile
        ## process logdir and support relative and absolute path
        logdir = process_log_dir(user_input_logdir, DEFAULT_LOG_DIR)
        latest_filename = get_log_file(logdir, user_input_logfile)
        print ("DEBUG: Main AgentBard Log Dir is %s, Log File is %s" % (str(logdir), str(latest_filename)) )      

        if latest_filename is None:
            print ("DEBUG: get_agentboard return empty logs from path %s" % logdir)
            return 

        latest_filepath = os.path.join(logdir, latest_filename)
        print ("DEBUG: AgentBoard Loading logs from path %s" % latest_filepath)


        # read file utf-8
        log_dict_list = [] 
        agent_log_dict = {}   # KV, K1: agent_name, K2: list
        data_type_set = set()        
        with codecs.open(latest_filepath, 'r', encoding='utf-8') as file:
            # Read all contents of the file
            for line in file:
                line = line.strip()
                try:
                    line_json = json.loads(line)
                    if line_json["data_type"] != DATA_TYPE_WORKFLOW:
                        # only filter out the logs with data_type 'workflow'
                        continue
                    cur_agent_name = line_json["agent_name"] if "agent_name" in line_json else ""
                    cur_data_type = line_json["data_type"] if "data_type" in line_json else ""
                    data_type_set.add(cur_data_type)
                    # only filter the required data_type
                    if cur_agent_name in agent_log_dict:
                        log_dict_list = agent_log_dict[cur_agent_name]
                        log_dict_list.append(line_json)
                        agent_log_dict[cur_agent_name] = log_dict_list
                    else:
                        agent_log_dict[cur_agent_name] = [line_json]
                except Exception as e:
                    print (e)
        ## visualize the log_dict_list, split by type
        for agent_name, log_dict_list in agent_log_dict.items():
            ## sort activity according to dict, increasing order
            log_dict_list_sorted = sorted(log_dict_list, key=lambda x:x["timestamp"])
            workflow_dict[agent_name] = log_dict_list_sorted

        ## filter
        # type_list = list(data_type_set)
        ## DEBUG: default set first data_type
        # datatype_list = datatype_group[type_list[0]] if len(type_list) > 0 else []
    except Exception as e:
        print (e)
    return render_template('agentboard_workflow.html', data = workflow_dict, types = type_list)


@app.route('/log/agent_loop', methods=['GET'])
def get_agent_loop():
    """
    """
    logdata_list = []
    type_list = BOARD_TYPE_LIST
    workflow_dict = {}
    try:
        global user_input_logdir
        global user_input_logfile
        ## process logdir and support relative and absolute path
        logdir = process_log_dir(user_input_logdir, DEFAULT_LOG_DIR)
        latest_filename = get_log_file(logdir, user_input_logfile)
        print ("DEBUG: Main AgentBard Log Dir is %s, Log File is %s" % (str(logdir), str(latest_filename)) )      

        if latest_filename is None:
            print ("DEBUG: get_agentboard return empty logs from path %s" % logdir)
            return 

        latest_filepath = os.path.join(logdir, latest_filename)
        print ("DEBUG: AgentBoard Loading logs from path %s" % latest_filepath)

        # read file utf-8
        log_dict_list = [] 
        agent_log_dict = {}   # KV, K1: agent_name, K2: list
        data_type_set = set()        
        with codecs.open(latest_filepath, 'r', encoding='utf-8') as file:
            # Read all contents of the file
            for line in file:
                line = line.strip()
                try:
                    line_json = json.loads(line)
                    if line_json["data_type"] != DATA_TYPE_AGENT_LOOP:
                        # only filter out the logs with agent_loop data_type
                        continue
                    cur_agent_name = line_json["agent_name"] if "agent_name" in line_json else ""
                    cur_data_type = line_json["data_type"] if "data_type" in line_json else ""
                    
                    data_type_set.add(cur_data_type)
                    # only filter the required data_type
                    if cur_agent_name in agent_log_dict:
                        log_dict_list = agent_log_dict[cur_agent_name]
                        log_dict_list.append(line_json)
                        agent_log_dict[cur_agent_name] = log_dict_list
                    else:
                        agent_log_dict[cur_agent_name] = [line_json]
                except Exception as e:
                    print (e)

        ## visualize the log_dict_list, split by type
        for agent_name, log_dict_list in agent_log_dict.items():
            ## sort activity according to dict, increasing order
            log_dict_list_sorted = sorted(log_dict_list, key=lambda x:x["timestamp"])
            workflow_dict[agent_name] = log_dict_list_sorted

        ## filter
        # type_list = list(data_type_set)
        ## DEBUG: default set first data_type
        # datatype_list = datatype_group[type_list[0]] if len(type_list) > 0 else []
    except Exception as e:
        print (e)
    return render_template('agentboard_workflow.html', data = workflow_dict, types = type_list)




# @app.route('/log/rag', methods=['GET'])
# def get_rag_workflow():
#     """
#     """
#     logdata_list = []
#     type_list = BOARD_TYPE_LIST
#     workflow_dict = {}
#     try:
#         global user_input_logdir
#         global user_input_logfile
#         ## process logdir and support relative and absolute path
#         logdir = process_log_dir(user_input_logdir, DEFAULT_LOG_DIR)
#         latest_filename = get_log_file(logdir, user_input_logfile)
#         print ("DEBUG: Main AgentBard Log Dir is %s, Log File is %s" % (str(logdir), str(latest_filename)) )      
#         if latest_filename is None:
#             print ("DEBUG: get_agentboard return empty logs from path %s" % logdir)
#             return 

#         latest_filepath = os.path.join(logdir, latest_filename)
#         print ("DEBUG: AgentBoard Loading logs from path %s" % latest_filepath)

#         # read file utf-8
#         log_dict_list = [] 
#         agent_log_dict = {}   # KV, K1: agent_name, K2: list
#         data_type_set = set()        
#         with codecs.open(latest_filepath, 'r', encoding='utf-8') as file:
#             # Read all contents of the file
#             for line in file:
#                 line = line.strip()
#                 try:
#                     line_json = json.loads(line)
#                     #@ add more field for display 
#                     query_list = line_json["data"]["input"]["query"]
#                     embedding_list = line_json["data"]["input"]["embedding"]
#                     pair_list = []
#                     for query, emb in zip(query_list, embedding_list):
#                         emb_str = ",".join(["{:.2f}".format(w) for w in emb])
#                         pair_list.append((query, emb_str))
#                     line_json["data"]["input"]["pair"] = pair_list

#                     if line_json["data_type"] != DATA_TYPE_RAG:
#                         # only filter out the logs with agent_loop data_type
#                         continue
#                     cur_agent_name = line_json["agent_name"] if "agent_name" in line_json else ""
#                     cur_data_type = line_json["data_type"] if "data_type" in line_json else ""
#                     data_type_set.add(cur_data_type)
#                     # only filter the required data_type
#                     if cur_agent_name in agent_log_dict:
#                         log_dict_list = agent_log_dict[cur_agent_name]
#                         log_dict_list.append(line_json)
#                         agent_log_dict[cur_agent_name] = log_dict_list
#                     else:
#                         agent_log_dict[cur_agent_name] = [line_json]
#                 except Exception as e:
#                     print (e)

#         ## visualize the log_dict_list, split by type
#         for agent_name, log_dict_list in agent_log_dict.items():
#             ## sort activity according to dict, increasing order
#             log_dict_list_sorted = sorted(log_dict_list, key=lambda x:x["timestamp"])
#             workflow_dict[agent_name] = log_dict_list_sorted
#         ## filter
#         # type_list = list(data_type_set)
#         ## DEBUG: default set first data_type
#         # datatype_list = datatype_group[type_list[0]] if len(type_list) > 0 else []
#     except Exception as e:
#         print (e)
#     return render_template('agentboard_rag.html', data = workflow_dict, types = type_list)

# Route to handle incoming requests and add them to the queue
@app.route('/agent/activities', methods=['POST'])
def post_agent_activity():
    """
        args: json list of dict, format:
            [{
                "role": "assistant",
                "content": "Swimming Class",
                "name": "Walle",
                "log_time": "2024-11-08 14:00"     
            }]
    """
    try:
        json_list = request.get_json()
        print ("DEBUG: Post Request Json List: %s" % str(json_list))
        insert_sql_query = "INSERT INTO agent_activity (log_time, agent_id, agent_name, role, content, status, ext_info) VALUES (?,?,?,?,?,?,?)"
        # write to db
        global user_input_db_dir
        global user_input_db_file
        db_path = get_db_file(user_input_db_dir, user_input_db_file)
        with app.app_context():
            succ_cnt, fail_cnt = 0, 0
            record = 0
            for data in json_list:
                record += 1
                if type(data) is not dict:
                    continue
                role = data["role"] if "role" in data else ""
                content = data["content"] if "content" in data else ""
                name = data["name"] if "name" in data else ""
                log_time = data["log_time"] if "log_time" in data else ""
                status = 2
                ext_info = ""
                args = (log_time, name, name, role, content, status, ext_info)
                db_status = insert_db_sql(db_path, insert_sql_query, args)
                print ("DEBUG: Post Request Json List Record %d|Status %d|Query %s|args %s" % (record, db_status, insert_sql_query, str(args)))
                if db_status == 1:
                    succ_cnt += 1
                else:
                    fail_cnt += 1            
            msg = "Inserting Agent Activities to DB success cnt %d, fail cnt %d" % (succ_cnt, fail_cnt)
            print (msg)
            code_success = 200
            data ={"code": code_success, "msg": msg}
        return jsonify(data)

    except Exception as e:
        print (e)
        s = traceback.format_exc()
        print (s)
        data ={"code": 404, "msg": "Request Failed..."}
        return jsonify(data)

# Route to handle incoming requests and add them to the queue
@app.route('/agent/user/add', methods=['POST'])
def post_agent_add_user():
    """
        args: json list of dict, format:
            [{
                "id": "assistant",
                "name": "xxx",
                "avatar": "/xxx.jpg",
                "password": ""     
            }]
    """
    try:
        json_list = request.get_json()
        print ("DEBUG: Post Request Json List: %s" % str(json_list))
        sql = "INSERT INTO user_profile (id, name, avatar, password, ext_info) VALUES (?,?,?,?,?)"
        # connect to db
        global user_input_db_dir
        global user_input_db_file
        db_path = get_db_file(user_input_db_dir, user_input_db_file)
        with app.app_context():
            succ_cnt, fail_cnt = 0, 0
            record = 0
            for data in json_list:
                record += 1
                if type(data) is not dict:
                    continue
                uid = data["id"] if "id" in data else ""
                name = data["name"] if "name" in data else ""
                avatar = data["avatar"] if "avatar" in data else ""
                password = data["password"] if "password" in data else ""
                ext_info = ""
                args = (uid, name, avatar, password, ext_info)
                db_status = insert_db_sql(db_path, sql, args)
                print ("DEBUG: Post /agent/user/add Request Json List Record %d|Status %d|Query %s|args %s" % (record, db_status, sql, str(args)))
                if db_status == 1:
                    succ_cnt += 1
                else:
                    fail_cnt += 1            
            msg = "Inserting Agent Add to DB success cnt %d, fail cnt %d" % (succ_cnt, fail_cnt)
            print (msg)
            code_success = 200
            data ={"code": code_success, "msg": msg}
        return jsonify(data)

    except Exception as e:
        print (e)
        s = traceback.format_exc()
        print (s)
        data ={"code": 404, "msg": "Request Failed..."}
        return jsonify(data)

@app.route('/x', methods=['GET'])
def page_x():
    return render_template('x.html')

def append_agent_activity_uri(activity_dict):
    """
    """
    agent_id = activity_dict["agent_id"] if "agent_id" in activity_dict else ""
    content_id = activity_dict["content_id"] if "content_id" in activity_dict else ""
    content_uri = "/agent/" + agent_id.lower() + "/" + str(content_id)
    return content_uri

@app.route('/agent', methods=['GET'])
def get_agent_activity_all():
    """
        {
            "activity_id": 1,
            "gmt_created": datetime.datetime(2024, 11, 8, 9, 3, 42),
            "log_time": datetime.datetime(2024, 11, 8, 9, 0),
            "agent_id": "Walle",
            "agent_name": "Walle",
            "role": "assistant",
            "content": "Having Breakfast",
            "ext_info": ''
        }
    """
    query_agent_activity_sql = """
        SELECT t1.activity_id AS content_id, CAST(t1.log_time AS TEXT) AS log_time, t1.agent_id, t1.agent_name, t1.role, t1.content, t1.status, t1.ext_info, t2.avatar, COALESCE(t3.comment_cnt, 0) AS comment_cnt
        FROM agent_activity t1 
        LEFT JOIN user_profile t2 
        ON t1.agent_id = t2.id
        LEFT JOIN 
        (
            SELECT to_id, count(1) AS comment_cnt
            FROM comment
            GROUP BY to_id
        ) t3 
        ON t1.activity_id = t3.to_id
    """
    items = []

    # connect to db
    global user_input_db_dir
    global user_input_db_file
    db_path = get_db_file(user_input_db_dir, user_input_db_file)

    with app.app_context():
        db = get_db(db_path)
        for activity in query_db(query_agent_activity_sql):
            # append URI
            activity["content_uri"] = append_agent_activity_uri(activity)
            items.append(activity)
    # debug 
    # print ("DEBUG: /agent return items %s" % str(items))
    return render_template('x_profile_main.html', items=items)

@app.route('/agent/<agent_id>', methods=['GET'])
def get_agent_profile_detail(agent_id):
    """
    """

    content_sql = """ 
        SELECT t1.activity_id AS content_id, CAST(t1.log_time AS TEXT) AS log_time, t1.agent_id, t1.agent_name
            , t1.role, t1.content, t1.status, t1.ext_info, t2.avatar, COALESCE(t3.comment_cnt, 0) AS comment_cnt
        FROM (
            SELECT *
            FROM agent_activity
            WHERE LOWER(agent_id) = "{agent_id}"
        ) t1 
        LEFT JOIN user_profile t2 
        ON t1.agent_id = t2.id 
        LEFT JOIN 
        (
            SELECT to_id, count(1) AS comment_cnt
            FROM comment
            GROUP BY to_id
        ) t3 
        ON t1.activity_id = t3.to_id
    """.format(agent_id=agent_id.lower())
    # print (content_sql)
    content_list = []

    # connect to db
    global user_input_db_dir
    global user_input_db_file
    db_path = get_db_file(user_input_db_dir, user_input_db_file)

    with app.app_context():
        db = get_db(db_path)
        for activity in query_db(content_sql):
            activity["content_uri"] = append_agent_activity_uri(activity)
            content_list.append(activity)
    # debug 
    return render_template('x_profile_main.html', items=content_list)
    # return render_template('agent_activities.html', items=items)

@app.route('/agent/<agent_id>/<content_id>', methods=['GET'])
def get_agent_post_detail(agent_id, content_id):
    """
    """
    # sql = 'select activity_id AS content_id, CAST(log_time AS TEXT) AS log_time, agent_id, agent_name, role, content, status, ext_info from agent_activity WHERE LOWER(agent_id) = "{agent_id}"'.format(agent_id=agent_id)
    content_sql = """ 
        SELECT t1.activity_id AS content_id, CAST(t1.log_time AS TEXT) AS log_time, t1.agent_id, t1.agent_name
            , t1.role, t1.content, t1.status, t1.ext_info, t2.avatar, COALESCE(t3.comment_cnt, 0) AS comment_cnt
        FROM (
            SELECT *
            FROM agent_activity
            WHERE LOWER(agent_id) = "{agent_id}"
            AND LOWER(activity_id) = "{content_id}"
        ) t1 
        LEFT JOIN user_profile t2 
        ON t1.agent_id = t2.id 
        LEFT JOIN 
        (
            SELECT to_id, count(1) AS comment_cnt
            FROM comment
            GROUP BY to_id
        ) t3 
        ON t1.activity_id = t3.to_id
    """.format(agent_id=agent_id.lower(), content_id=content_id)
    # print (content_sql)

    # connect to db
    global user_input_db_dir
    global user_input_db_file
    db_path = get_db_file(user_input_db_dir, user_input_db_file)

    content_list = []
    with app.app_context():
        db = get_db(db_path)
        for content in query_db(content_sql):
            content_list.append(content)
    print ("DEBUG: Agent %s Post %s" % (agent_id, str(content_list)))
    # unique content id
    post = content_list[0] if len(content_list) > 0 else None

    # comment
    comment_sql = """ 
        SELECT t1.comment_id, CAST(t1.log_time AS TEXT) AS log_time, t1.to_id, t1.user_id, t1.content, t1.ext_info, t2.avatar 
        FROM comment t1 
        LEFT JOIN user_profile t2 
        ON t1.user_id = t2.id 
        WHERE to_id="{content_id}"  
    """.format(content_id=content_id)
    print (comment_sql)
    comment_items = []
    with app.app_context():
        db = get_db(db_path)
        for activity in query_db(comment_sql):
            comment_items.append(activity)
    # debug 
    # print ("DEBUG: len(items) is %d" % len(comment_items))
    return render_template('x_post_detail.html', comments=comment_items, post=post)


### GET Function PENDING COMMENT
@app.route('/agent/activities/pending', methods=['GET'])
def get_agent_activities_pending():
    """
        {
            "activity_id": 1,
            "gmt_created": datetime.datetime(2024, 11, 8, 9, 3, 42),
            "log_time": datetime.datetime(2024, 11, 8, 9, 0),
            "agent_id": "Walle",
            "agent_name": "Walle",
            "role": "assistant",
            "content": "Having Breakfast",
            "ext_info": ''
        }
    """
    # connect to db
    global user_input_db_dir
    global user_input_db_file
    db_path = get_db_file(user_input_db_dir, user_input_db_file)

    sql = 'select activity_id AS content_id, CAST(log_time AS TEXT) AS log_time, agent_id, agent_name, role, content, status, ext_info from agent_activity where status = 2;'
    items = []
    with app.app_context():
        db = get_db(db_path)
        for activity in query_db(sql):
            items.append(activity)
    return jsonify(items)

@app.route('/agent/activities/new', methods=['GET'])
def get_agent_activities_new():
    """
        Get all the newly published comment within 30 minutes publish time
        {
            "activity_id": 1,
            "gmt_created": datetime.datetime(2024, 11, 8, 9, 3, 42),
            "log_time": datetime.datetime(2024, 11, 8, 9, 0),
            "agent_id": "Walle",
            "agent_name": "Walle",
            "role": "assistant",
            "content": "Having Breakfast",
            "ext_info": ''
        }
        time_range_secs: e.g. 1 days or 24 hours
        strftime("%s", log_time): str
        CAST(strftime("%s", log_time) AS INTEGER): int
    """
    # time_range_secs =  24 * 60 * 60
    # connect to db
    global user_input_db_dir
    global user_input_db_file
    db_path = get_db_file(user_input_db_dir, user_input_db_file)

    sql = """ 
            SELECT t3.*
            FROM
            (
              SELECT t1.*, t2.comment_cnt
              FROM
              (
                SELECT activity_id AS content_id, agent_id, agent_name, role, content, status, ext_info
                FROM agent_activity 
                WHERE status=1
              ) t1 
              LEFT JOIN
              (
                SELECT to_id AS content_id, count(*) AS comment_cnt
                FROM comment
                GROUP BY to_id
              ) t2 
              ON t1.content_id = t2.content_id
            ) t3 
            WHERE t3.comment_cnt IS NULL
    """
    # print ("DEBUG: get_agent_comments_new sql is %s" % sql)
    items = []
    with app.app_context():
        db = get_db(db_path)
        for activity in query_db(sql):
            items.append(activity)
    print ("DEBUG: get_agent_comments_new is %s" % str(items))
    return jsonify(items)

### POST Update Status
@app.route('/agent/activities/update', methods=['POST'])
def post_activities_update():
    # request_queue.put("new request")
    """
        args: json list of dict, format:
            [{"user_id": user_id, "content_id": content_id, "status": status}]
    """
    try:

        # connect to db
        global user_input_db_dir
        global user_input_db_file
        db_path = get_db_file(user_input_db_dir, user_input_db_file)

        json_list = request.get_json()
        print ("DEBUG: Post Request Json List: %s" % str(json_list))
        sql = "UPDATE agent_activity SET status=? WHERE activity_id=?"
        # write to db
        with app.app_context():
            succ_cnt, fail_cnt = 0, 0

            record = 0
            for data in json_list:
                record += 1
                if type(data) is not dict:
                    continue
                # content_id: int
                # status: int
                content_id = data["content_id"] if "content_id" in data else None
                status = data["status"] if "status" in data else None
                if content_id is None or status is None:
                    continue
                args = (status, content_id)
                db_status = insert_db_sql(db_path, sql, args)
                print ("DEBUG: Post Request Json List Record %d|Status %d|Query %s|args %s" % (record, db_status, sql, str(args)))
                if db_status == 1:
                    succ_cnt += 1
                else:
                    fail_cnt += 1            
            msg = "Inserting Comment Activities to DB success cnt %d, fail cnt %d" % (succ_cnt, fail_cnt)
            print (msg)
            code_success = 200
            data ={"code": code_success, "msg": msg}
        return jsonify(data)

    except Exception as e:
        print (e)
        s = traceback.format_exc()
        print (s)
        data ={"code": 404, "msg": "Request Failed..."}
        return jsonify(data)


#### POST add Comment 
@app.route('/agent/comment/add', methods=['POST'])
def post_comment_add():
    # request_queue.put("new request")
    """
        args: json list of dict, format:
            [{"user_id": user_id, "content_id": content_id, "status": status}]
    """
    try:
        # connect to db
        global user_input_db_dir
        global user_input_db_file
        db_path = get_db_file(user_input_db_dir, user_input_db_file)

        json_list = request.get_json()
        print ("DEBUG: Post Request Json List: %s" % str(json_list))
        if not isinstance(json_list, list):
            data = {"code": 404, "msg": "Input Args Not Json List Format..."}
            return jsonify(data)
        if len(json_list) == 0:
            data = {"code": 404, "msg": "Input Args Json List empty size 0...."}
            return jsonify(data)
        sql = "INSERT INTO comment (to_id, log_time, user_id, content, ext_info) VALUES (?,?,?,?,?)"
        with app.app_context():
            succ_cnt, fail_cnt = 0, 0
            record = 0
            for data in json_list:
                record += 1
                if type(data) is not dict:
                    continue

                to_id = data["to_id"] if "to_id" in data else None
                log_time = data["log_time"] if "log_time" in data else None
                user_id = data["user_id"] if "user_id" in data else None
                content = data["content"] if "content" in data else None
                ext_info = data["ext_info"] if "ext_info" in data else None

                if to_id is None or log_time is None or user_id is None or content is None or ext_info is None:
                    continue
                args = (to_id, log_time, user_id, content, ext_info)
                db_status = insert_db_sql(db_path, sql, args)
                print ("DEBUG: Post Request Json List Record %d|Status %d|Query %s|args %s" % (record, db_status, sql, str(args)))
                if db_status == 1:
                    succ_cnt += 1
                else:
                    fail_cnt += 1            
            msg = "Inserting Reply to DB success cnt %d, fail cnt %d" % (succ_cnt, fail_cnt)
            print (msg)
            code_success = 200
            data ={"code": code_success, "msg": msg}
        return jsonify(data)

    except Exception as e:
        print (e)
        s = traceback.format_exc()
        print (s)
        data ={"code": 404, "msg": "Request Failed..."}
        return jsonify(data)


@app.route('/agent/comment', methods=['GET'])
def get_all_comment():
    """
    """
    sql = 'select comment_id AS content_id, CAST(log_time AS TEXT) AS log_time, to_id, user_id, content, ext_info from comment'
    # connect to db
    global user_input_db_dir
    global user_input_db_file
    db_path = get_db_file(user_input_db_dir, user_input_db_file)

    items = []
    with app.app_context():
        db = get_db(db_path)
        for activity in query_db(sql):
            items.append(activity)
    # debug 
    print ("DEBUG: len(items) is %d" % len(items))
    for i, activity in enumerate(items):
        print ("DEBUG: get_all_comment data Format %s" % str(activity))
    return render_template('comments.html', items=items)

def run_command_line():
    """
        main entry point function of pip

        agentboard --logdir xxx 
        e.g. tensorboard --logdir=summaries

    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--logdir', type=str, default = DEFAULT_LOG_DIR)
    parser.add_argument('--logfile', type=str, default = None)
    parser.add_argument('--static', type=str, default = DEFAULT_STATIC_DIR)
    parser.add_argument('--db_dir', type=str, default = DEFAULT_DB_DIR)
    parser.add_argument('--db_file', type=str, default = DEFAULT_DB_FILE_SQLITE)
    parser.add_argument('--port', type=str, default = None)
    args = parser.parse_args()

    global user_input_logdir
    global user_input_logfile
    global user_input_static_dir
    global user_input_db_dir
    global user_input_db_file

    user_input_logdir = args.logdir
    user_input_logfile = args.logfile
    user_input_static_dir = args.static
    user_input_db_dir = args.db_dir
    user_input_db_file = args.db_file

    port = args.port if args.port is not None else FLASK_PORT
    print ("DEBUG: CLI Command Ling input arg logdir %s" % str(user_input_logdir))
    print ("DEBUG: CLI Command Ling input arg logfile %s" % str(user_input_logfile))
    print ("DEBUG: CLI Command Ling input arg static %s" % str(user_input_static_dir))
    print ("DEBUG: CLI Command Ling input arg db_dir %s" % str(user_input_db_dir))
    print ("DEBUG: CLI Command Ling input arg db_file %s" % str(user_input_db_file))
    print ("DEBUG: CLI Command Ling input arg port %s" % str(port))

    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":

    # Start the Flask web server
    # app.run(debug=True)
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=True)    
