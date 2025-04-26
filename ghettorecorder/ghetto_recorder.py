"""File system tasks module.

:methods: accumulate_chunks: Append chunks to rec file
:methods: switch_title: Write last, first chunk of new, dump old file to disc.
:methods: teardown: Graceful copy, mark files incomplete on shut down.
:methods: copy_dst: Decide if recorder file should be dumped or not.

:methods: rename_dst: Renames existing file for shutil copy.
:methods: copy_src_dst: Copy recorder file to user file
:methods: bin_writer_reset_file_offset: Reset file writer offset to begin of file
:methods: record_write_first: first chunk for file head, will be repaired if aac
:methods: record_write_last: last chunk for file tail, will be repaired if aac
:methods: write_queue_listen: empty the Queue if full and write new chunk for listen to web server
:methods: drain_queue_listen: remove all chunks from queue to drain html audio element
:methods: this_time: tells current date, time for dummy file, if no metadata is sent by radio
"""

import os
import pathlib
import shutil
import time

from aacrepair import AacRepair

aac_repair = AacRepair()


def teardown(str_radio, bin_writer, rec_src, rec_dst):
    """Graceful copy, mark files incomplete at shut down.

    :params: str_radio: radio name
    :params: rec_src : name of the recorder file in OS syntax, needed in if-clause to copy to physical path
    :params: bin_writer: alias of with statement for writing to recorder file
    :params: rec_dst: absolute path to user file
    :exception: OSError on disk fail or folder not writeable
    """

    try:
        head, tail = os.path.split(rec_dst)
        incomplete_title = bytes("_incomplete_", 'utf-8') + tail.encode('utf-8')
        last_title = os.path.join(head.encode('utf-8'), incomplete_title)
    except Exception as error:
        print(f"Unknown error: {str_radio} {error} - last file not dumped.")
        return

    try:
        shutil.copyfile(rec_src, last_title)
    except OSError:
        pass
    print(f" ..%-10s\t last file: {last_title}" % str_radio)

    try:
        bin_writer.seek(0)
        bin_writer.truncate()
        bin_writer.flush()
        bin_writer.close()
    except Exception as error:
        print(f'--> {str_radio} {error}')
        return


def path_title_cut(str_radio, rec_dst):

    try:
        path, file_name = os.path.split(rec_dst)
        name_list = file_name.split('.')
        title = name_list[0]
        suffix = name_list[1]
    except Exception as error:
        print(f"Unknown error: {str_radio} {error} - last file not dumped.")
        return
    rv_dict = {'path': path, 'file_name': file_name, 'title': title, 'suffix': suffix}
    return rv_dict


def copy_skip(str_radio, recorder_dst):
    """Show skipped file path

    :params: str_radio: name
    :params: recorder_dst: absolute path to user file
    """
    print(f'\n-SKIP->>> {str_radio}: {recorder_dst.encode("utf-8")}\n')


def copy_dst(str_radio, recorder_dst, bin_writer, recorder_src, buf_size):
    """
    Caller. Call only if attribute is set. 'recorder_file_write'

    :params: str_radio: name
    :params: recorder_dst: absolute path to user file
    :params: bin_writer: instance of the open recorder file
    :params: recorder_src: absolute path to recorder file
    :params: buf_size: chunk size to fit block size of OS
    """
    try:
        rename_dst(recorder_dst, bin_writer)
        copy_src_dst(recorder_dst, recorder_src, buf_size)
        print(f'\n-WRITE->>> {str_radio}: {recorder_dst.encode("utf-8")}\n')
    except Exception as e:
        print("Unusual error in mod ghetto_recorder.py, Android?", e)


def rename_dst(rec_dst, bin_writer):
    """Rename existing file for shutil copy.

    :params: rec_dst: absolute path to user file
    :params: bin_writer: instance of the open recorder file
    :rtype: True
    """
    try:
        dst_file = pathlib.Path(rec_dst)
        if dst_file.is_file():
            new_name = f"{dst_file.stem}.{int(time.time())}{dst_file.suffix}"
            dst_file.rename(pathlib.Path(dst_file.parent, new_name))
    except AttributeError:
        return False
    bin_writer.flush()


def copy_src_dst(rec_dst, rec_src, buf_size):
    """Copy recorder file to user file.
    File must be bigger than one chunk of radio stream.

    :params: rec_src: absolute path to recorder file
    :params: rec_dst: absolute path to user file
    :params: buf_size: chunk size to fit block size of OS
    :raise: OSError on disk fail or folder not writeable
     """
    ghetto_size = os.path.getsize(rec_src)
    if int(ghetto_size) >= int(buf_size):
        try:
            shutil.copyfile(rec_src, rec_dst.encode("utf-8"))
        except AttributeError:
            pass
        except OSError as error:
            message = f' Exception in copy_src_dst; error: {error}'
            print(message)
    else:
        print('Skip file - size is too small.')


def bin_writer_reset_file_offset(bin_writer):
    """Reset file writer offset to begin of file.

    :params: bin_writer: instance of the open recorder file
    """
    bin_writer.seek(0)
    bin_writer.truncate()


def record_write_first(chunk, bin_writer=None, suffix=None):
    """Return first head cleaned aac chunk after a title change, else mp3 dirty chunk.

    :params: chunk: part of http response stream
    :params: bin_writer: instance of the open recorder file
    :params: suffix: file suffix
    """
    if "aac" in suffix:
        chunk = aac_repair.repair_object(chunk, head=True) if chunk else None
    if bin_writer:
        write_recorder(chunk, bin_writer)
    return chunk


def record_write_last(chunk, bin_writer=None, suffix=None):
    """Have to fix aac file end (clean cut of last chunk) so title not stuck in a playlist.

    :params: chunk: part of http response stream
    :params: bin_writer: instance of the open recorder file
    :params: suffix: file suffix
    """
    if "aac" in suffix:
        chunk = aac_repair.repair_object(chunk, tail=True) if chunk else None
    if bin_writer:
        write_recorder(chunk, bin_writer)
    return chunk


def write_recorder(chunk, bin_writer):
    """Write chunks to the recorder file. Mp3 files are not repaired. Browser plays them.

    :exception: File already closed. chunk grabbed before and not written after recorder shutdown;
    :params: chunk: part of http response stream
    :params: bin_writer: instance of the open recorder file
    """
    if chunk:
        try:
            bin_writer.write(chunk)
        except ValueError:
            pass


def this_time():
    """Mark a recorded title if no metadata are available.

    :returns: date and time
    :rtype: str
    """
    time_val = time.strftime("_%Y_%m_%d_%H.%M.%S")
    return time_val


def generate_chunks(file_object, buf):
    """Generator function to break up a binary file.

    :params: file_obj: file system file
    :params: buf: buffer size to read
    :returns: buffer sized chunk
    :rtype: yield
    """
    bin_reader = open(file_object, 'rb')
    bin_reader.read()
    read_start = 0
    while 1:
        try:
            chunk = bin_reader[read_start:read_start + buf]
            read_start += buf
            if not len(chunk):  # StopIteration
                break
            yield chunk
        except Exception as e:
            print(f'Exception in generate_chunks() {e}')
        finally:
            bin_reader.close()
    bin_reader.close()
