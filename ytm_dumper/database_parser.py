import argparse
import base64
import datetime
import sqlite3
import blackboxprotobuf
from urllib.parse import unquote
from collections import namedtuple
import json

DEBUG = False
VIDEO_DETAILS = 119
CACHE_ELEMENT = 198

Video = namedtuple('Video', 'id,cache_key,title,artist,cover_url,mime,album,timestamp')

KeyProto = {
    "2": {"type": "string", "name": "key"}
}

FormatStreamProto = {
    "1": {"type": "int", "name": "itag"},
    "11": {"type": "int", "name": "timestamp"},
    "5": {"type": "string", "name": "mime_type"}
}

CacheElementProto = {
    "2": {
            "type": "message",
            "message_typedef": {
                "5": {
                    "type": "message",
                    "name": "format_stream",
                    "message_typedef": FormatStreamProto
                }
            }
    }
}

VideoDetailsProto = {
    "2": {
            "type": "message",
            "message_typedef": {
                "11": {
                    "type": "message",
                    "message_typedef": {
                        "15": {"type": "string", "name": "title"},
                        "33": {"type": "string", "name": "artist"},
                    }
                }
            }
    }
}


DATA_TYPES = {
    VIDEO_DETAILS: ('VideoDetails', VideoDetailsProto),
    CACHE_ELEMENT: ('FormatStream', CacheElementProto),
}

def decode_protobuf_message(raw_message: bytes, type_name: str, type_hint: dict, debug_info: str) -> dict:
    try:
        message, type_def = blackboxprotobuf.decode_message(raw_message, type_hint)
        if not type_hint:
            print(type_name, json.dumps(type_def, indent=2))
        return message
    except Exception as e:
        try:
            message, type_def = blackboxprotobuf.decode_message(raw_message)
        except:
            print(f"{debug_info}, Blob: {raw_message}, Error during raw decode: {e}")
            return
        print(json.dumps(type_def, indent=4))
        raise RuntimeError(f"{debug_info}, type_hint: {type_name}({type_hint}) does not match message", e)

# 169: ["2"]["3"]["356057097"]["3"]["22"] -> album
class EntityStore(object):
    def __init__(self, db_filename: str, since: datetime.datetime):
        data = self.data = {}

        conn = sqlite3.connect(db_filename)
        cursor = conn.cursor()

        condition = '1'
        if since:
            condition += f" AND last_modified_datetime >= {int(since.timestamp()) * 1000}"
        if DEBUG:
            condition += f' AND data_type IN ({VIDEO_DETAILS}, {CACHE_ELEMENT})'
        cursor.execute("SELECT key, data_type, entity, last_modified_datetime FROM entity_table WHERE " + condition)
        rows = cursor.fetchall()

        for row in rows:
            key, data_type, raw_entity, timestamp = row
            
            if DEBUG:
                boring_types = [
                    VIDEO_DETAILS,
                    CACHE_ELEMENT,
                    120, # transfer entity
                    197, # local image
                    62, # ???
                    557, # lyrics?
                    130, # offline policy
                    169
                ]
                if data_type not in boring_types:
                    print('data_type', data_type)
                    import pprint
                    pprint.pprint(blackboxprotobuf.decode_message(raw_entity)[0])
                if data_type == 169:
                    message = blackboxprotobuf.decode_message(raw_entity)[0]
                    print(key, 'album', message["2"]["3"].get("356057097", {}).get("3", {}).get("22", ''))
                continue

            if data_type not in (VIDEO_DETAILS, CACHE_ELEMENT):
                continue

            try:
                key = decode_protobuf_message(base64.b64decode(unquote(key)), 'Key', KeyProto, f'key={key}, key_proto')
                key = key["key"]  # youtubeId
            except Exception as e:
                print(f"Error decoding entity for key '{key}': {e}")
                raise

            type_name, type_hint = DATA_TYPES[data_type]
            message = decode_protobuf_message(row[2], type_name, type_hint, f"Key: {key}, Data Type: {data_type}")
            if message:
                entry = data.setdefault(key, {})
                entry[data_type] = message
                if data_type == VIDEO_DETAILS:
                    entry["timestamp"] = timestamp

        if conn:
            conn.close()
    
    def __iter__(self):
        for k, v in self.data.items():
            if not VIDEO_DETAILS in v:
                if DEBUG:
                    print('-V--->', k)
                continue
            details = v[VIDEO_DETAILS]["2"]["11"]
            if not CACHE_ELEMENT in v:
                if DEBUG:
                    print('-C--->', k)
                continue
            cache = v[CACHE_ELEMENT]
            stream = cache["2"]
            if type(stream) == list:
                stream = stream[0]
            stream = stream["format_stream"]
            # select the largest cover url
            cover_url = max(details["25"]["1"], key=lambda x: x["2"])["1"]
            yield Video(
               id=k,
               cache_key=b'%s.%d.%d' % (k.encode('ascii'), stream["itag"], stream["timestamp"]),
               title=details["title"],
               artist=details["artist"],
               cover_url=cover_url,
               mime=stream["mime_type"],
               album=v.get("56", ''),
               timestamp=v.get('timestamp'),
            )

OfflineVideoDataProto = {
        "2": {
            "type": "message",
            "message_typedef": {
                "1": {
                    "type": "message",
                    "name": "covers",
                    "message_typedef": {
                        "1": {"type": "string", "name": "url"},
                        "2": {"type": "int", "name": "height"},
                        "3": {"type": "int", "name": "width"}
                    }
                }
            }
        },
        "14": {
            "type": "message",
            "message_typedef": {
                "112520939": {
                    "type": "message",
                    "name": "metadata",
                    "message_typedef": {
                        "1": {"type": "string", "name": "title"},
                        "2": {"type": "string", "name": "title_shortened"},
                        "3": {"type": "string", "name": "artist"},
                    }
                }
            }
        }
    }

class OfflineVideoDb(object):
    def __init__(self, db_filename: str, since: datetime.datetime):
        self.data = {}
        conn = sqlite3.connect(db_filename)
        cursor = conn.cursor()

        condition = ''
        if since:
            condition = f" AND saved_timestamp >= {int(since.timestamp()) * 1000}"
        cursor.execute("SELECT id, offline_video_data_proto, format_stream_proto, saved_timestamp FROM videosV2, streams WHERE id=video_id" + condition)
        rows = cursor.fetchall()

        for row in rows:
            key = row[0]
            video = decode_protobuf_message(row[1], 'OfflineVideoData', OfflineVideoDataProto, f'key={key}, offline_video_data_proto')
            stream = decode_protobuf_message(row[2], 'FormatStream', FormatStreamProto, f'key={key}, format_stream_proto')
            timestamp = row[3]

            self.data[key] = (video, stream, timestamp)

        if conn:
            conn.close()

    def __iter__(self):
        for k, v in self.data.items():
            stream = v[1]
            details = v[0]["14"]["metadata"]
            covers = v[0]["2"]["covers"]
            if not isinstance(covers, list): covers = [covers]
            # select the largest cover url
            cover_url = max(covers, key=lambda x: x["height"])["url"]

            yield Video(
               id=k,
               cache_key=b'%s.%d.%d' % (k.encode('ascii'), stream["itag"], stream["timestamp"]),
               title=details["title"],
               artist=details.get("artist"),
               cover_url=cover_url,
               mime=stream["mime_type"],
               album=None,
               timestamp=v[2]
            )

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Dump Youtube Music exo cache music/videos from a rooted Android phone.")
    parser.add_argument("--entity_store", help="Path to the .entitystore sqlite3 database.")
    parser.add_argument("--offline_db", help="Path to the offline*.db sqlite3 database.")
    parser.add_argument("-d", "--debug", action="store_true")
    args = parser.parse_args()

    entity_store = args.entity_store and EntityStore(args.entity_store)
    offline_db = args.offline_db and OfflineVideoDb(args.offline_db)

    if args.debug:
        import pprint
        pprint.pprint(entity_store and entity_store.data)
        pprint.pprint(offline_db and offline_db.data)

    
    if entity_store:
        for video in entity_store:
            print(video)
    if offline_db:
        for video in offline_db:
            print(video)