"""Recorder may write only if current title is not in blacklist.

| Update a json dict file in intervals, like it eisenradio in database does.
| All radio instance lists are stored in memory. A copy of the json file.
| Write to fs json dictionary if change occurs. Updates mem list.

| All communication via multiprocessor queues.
| Blacklist module reads title from radio instance
| and disables the radio write attribute, if json blacklist title matches.
"""
import os.path
import time
import json
import threading
from pathlib import Path

import ghettorecorder.ghetto_procenv as procenv
from ghettorecorder.ghetto_api import ghettoApi


class Helper:
    def __init__(self):
        self.radio_name_list = []
        self.config_file_radio_url_dict = {}
        self.blacklist_name = ''
        self.blacklist_dir = ''  # changed if settings GLOBAL 'save_to_dir' changes, blacklist_dir is that dir
        self.title_wait_blacklist_dct = {}


helper = Helper()


def init(**kwargs):
    """kwargs is the dump of callers instances dict
    Blacklist is driven by the main() thread, com with procs via com_in, com_out of instance.
    com_in is eval, exec
    com_out delivers the result of eval, or None if exec is done, or error msg
    """
    helper.blacklist_name = kwargs['blacklist_name']
    helper.blacklist_dir = kwargs['config_dir']  # changed from parent_dir to keep config and blacklist together
    helper.radio_name_list = kwargs['radio_name_list']
    helper.config_file_radio_url_dict = kwargs['config_file_radio_url_dict']

    true_list = [True, 'y', 'Y', 'yes', 'Yes', 'YES', 'true', 'True', 'TRUE', '1']
    ghettoApi.blacklist.blacklist_enable = kwargs['config_file_settings_dict']['blacklist_enable'] in true_list
    if ghettoApi.blacklist.blacklist_enable:
        blacklist_enable(kwargs['blacklist_name'])


def blacklist_enable(file_name):
    """Prepare env for blacklist writer

    - get directory of config file to put blacklist in the same directory
    - call to write a new or update an existing blacklist with radios from config file
    - loads the reader json string from written file into the blacklist dictionary
    - writes the blacklist file name to the api, blacklist writer can update file
    - starts the blacklist writer daemon --> update, no daemon this guy can keep running after prog kill

    :params: blacklist_name: name
     """
    blacklist_dir = helper.blacklist_dir
    blacklist_written = write_blacklist(blacklist_dir, file_name)
    if blacklist_written:
        # return also ok if file exists
        with open(os.path.join(blacklist_dir, file_name), "r", encoding="UTF-8") as str_reader:
            str_json = str_reader.read()
        # write dict to api, each recorder can compare titles of its radio, json converts str to dict
        ghettoApi.blacklist.all_blacklists_dict = json.loads(str_json)
        start_ghetto_blacklist_writer_daemon()


def write_blacklist(bl_path, bl_name):
    """Write new or update blacklist with new radio names.

    :params: bl_path: path to blacklist
    :params: bl_name: name of blacklist json
    """
    path = os.path.join(bl_path, bl_name)
    if not Path(path).is_file():
        return True if populate_new_blacklist(path) else False
    else:
        return True if update_blacklist(path) else False


def populate_new_blacklist(path):
    """ return True if first time populate the blacklist with empty lists
    add new radios to the list, if list already exists

    | this will create a NEW blist
    | dump all radios from settings.ini
    | append a radio from dump list to blist, create first blist entry "was geht?"
    | write blist to fs

    :params: path: to blacklist
    :exception: make write error public
    :rtype: False
    """
    first_key = 'GhettoRecorder (Eisenradio compatible json) message'
    first_msg = 'A json formatted dictionary. Remove titles you want again.'
    radio_bl_dict = {first_key: [first_msg]}

    for name in helper.radio_name_list:
        radio_bl_dict[name] = ['GhettoRecorder - ¿qué pasa?']
    try:
        with open(path, 'w') as writer:
            writer.write(json.dumps(radio_bl_dict, indent=4))  # no indent is one long line
    except OSError as error:
        msg = f"\n\t--->>> error in populate_new_blacklist(), can not create {error} {path}"
        print(msg)
        return False
    return True


def update_blacklist(path):
    """ return True if update existing blacklist json
    read, load in dict, compare with actual settings.ini,
    update loaded dict, write dict

    | Alter an existing blist.
    | Dump all radios from settings.ini
    | Read in existing blacklist from fs
    | Append a radio from dump list to blist, if radio not in blist create first blist entry "was geht?"
    | Rewrite altered blist

    :params: path: to blacklist
    :exception: make write error public
    :rtype: False
    """
    with open(os.path.join(path), "r", encoding="UTF-8") as reader:
        bl_json_dict = reader.read()
    loaded_dict = json.loads(bl_json_dict)

    for radio in helper.radio_name_list:
        if radio not in loaded_dict.keys():
            loaded_dict[radio] = ['GhettoRecorder - ¿qué pasa?']
    try:
        with open(path, 'w', encoding="UTF-8") as writer:
            writer.write(json.dumps(loaded_dict, indent=4))  # no indent is one long line
    except OSError as error:
        msg = f"\n\t--->>> error in terminal_update_blacklist(), can not create {error} {path}"
        print(msg)
        return False
    return True


def start_ghetto_blacklist_writer_daemon():
    """Start a thread, runs forever"""
    threading.Thread(name="ghetto_blacklist_writer", target=run_blacklist_writer, daemon=False).start()
    print(".. blacklist writer daemon started\n")


def run_blacklist_writer():
    """loop, read "recorder_new_title_dict" in api and update json dict file for next session plus
    'ghettoApi.blacklist.all_blacklists_dict[str_radio]'
    """
    sleep_sec = 10
    while not ghettoApi.blacklist.stop_blacklist_writer:
        update_recorder_new_title_dict()
        update_radios_blacklists()

        for _ in range(sleep_sec):
            if ghettoApi.blacklist.stop_blacklist_writer:
                break
            time.sleep(1)


def update_recorder_new_title_dict():
    """Collect new_title attribute of all instances.
    Here we decide if updater writes new title to blacklist or not.

    If title not in blacklist, wait until next title to update blacklist.
    Recorder can write the title
    """
    radio_lst = [radio for radio in ghettoApi.radio_inst_dict.keys()]
    upd_blacklist_dct = ghettoApi.blacklist.recorder_new_title_dict  # updater writes to blacklist
    all_black_dct = ghettoApi.blacklist.all_blacklists_dict

    for radio in radio_lst:
        title = procenv.radio_attribute_get(radio=radio, attribute='new_title')
        title_wait = helper.title_wait_blacklist_dct
        if radio not in title_wait.keys():
            title_wait[radio] = None

        if title in all_black_dct[radio]:
            disable_recorder_write_file(radio)  # disable is valid for one call to 'copy_dst' method in instance
            upd_blacklist_dct[radio] = ''
            continue

        if title_wait[radio] != title:  # await next title to blacklist the 'written' title
            upd_blacklist_dct[radio] = title_wait[radio]  # updater writes mem and json fs, recorder wrote old title
            title_wait[radio] = title


def disable_recorder_write_file(radio):
    """"""
    procenv.radio_attribute_set(radio=radio, attribute='recorder_file_write', value='False')


def update_radios_blacklists():
    """Compare recorder_new_title_dict['radio5'] with all_blacklists_dict['radio5']"""

    for radio, new_title in ghettoApi.blacklist.recorder_new_title_dict.items():
        if new_title and new_title not in ghettoApi.blacklist.all_blacklists_dict[radio]:
            # json seems to write sporadic garbage if list is empty
            if not type(ghettoApi.blacklist.all_blacklists_dict[radio]) is list:
                ghettoApi.blacklist.all_blacklists_dict[radio] = []
            ghettoApi.blacklist.all_blacklists_dict[radio].append(new_title)  # AttributeError: 'dict' object has no
            try:
                print(f" -> blacklist {radio}: {new_title.encode('utf-8')}")
            except AttributeError:
                pass

            blacklist_file = os.path.join(helper.blacklist_dir, helper.blacklist_name)

            try:
                with open(blacklist_file, 'w', encoding="UTF-8") as writer:
                    writer.write(json.dumps(ghettoApi.blacklist.all_blacklists_dict, indent=4))  # no long line
            except OSError as error:
                msg = f"\n\t--->>> error in update_radios_blacklists(), can not create {error} {blacklist_file}"
                print(msg)
