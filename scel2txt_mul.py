"""
搜狗细胞词库转鼠须管（Rime）词库

搜狗的 scel 词库是按照一定格式保存的 Unicode 编码文件，其中每两个字节表示一个字符（中文汉字或者英文字母），主要两部分:

1. 全局拼音表，在文件中的偏移值是 0x1540+4, 格式为 (py_idx, py_len, py_str)
    - py_idx: 两个字节的整数，代表这个拼音的索引
    - py_len: 两个字节的整数，拼音的字节长度
    - py_str: 当前的拼音，每个字符两个字节，总长 py_len

2. 汉语词组表，在文件中的偏移值是 0x2628 或 0x26c4, 格式为 (word_count, py_idx_count, py_idx_data, (word_len, word_str, ext_len, ext){word_count})，其中 (word_len, word, ext_len, ext){word_count} 一共重复 word_count 次, 表示拼音的相同的词一共有 word_count 个
    - word_count: 两个字节的整数，同音词数量
    - py_idx_count:  两个字节的整数，拼音的索引个数
    - py_idx_data: 两个字节表示一个整数，每个整数代表一个拼音的索引，拼音索引数 
    - word_len:两个字节的整数，代表中文词组字节数长度
    - word_str: 汉语词组，每个中文汉字两个字节，总长度 word_len
    - ext_len: 两个字节的整数，可能代表扩展信息的长度，好像都是 10
    - ext: 扩展信息，一共 10 个字节，前两个字节是一个整数(不知道是不是词频)，后八个字节全是 0，ext_len 和 ext 一共 12 个字节

参考资料 
1. https://raw.githubusercontent.com/archerhu/scel2mmseg/master/scel2mmseg.py
2. https://raw.githubusercontent.com/xwzhong/small-program/master/scel-to-txt/scel2txt.py
"""
import struct
import os
import sys
import json
import urllib.request
import datetime

def read_utf16_str(f, offset=-1, len=2):
    if offset >= 0:
        f.seek(offset)
    string = f.read(len)
    return string.decode('UTF-16LE')


def read_uint16(f):
    return struct.unpack('<H', f.read(2))[0]


def get_hz_offset(f):
    mask = f.read(128)[4]
    if mask == 0x44:
        return 0x2628
    elif mask == 0x45:
        return 0x26c4
    else:
        print("不支持的文件类型(无法获取汉语词组的偏移量)")
        sys.exit(1)


def get_dict_meta(f):
    title = read_utf16_str(f, 0x130, 0x338 - 0x130)
    category = read_utf16_str(f, 0x338, 0x540 - 0x338)
    desc = read_utf16_str(f, 0x540, 0xd40 - 0x540)
    samples = read_utf16_str(f, 0xd40, 0x1540 - 0xd40)
    return title, category, desc, samples


def get_py_map(f):
    py_map = {}
    f.seek(0x1540+4)

    while True:
        py_idx = read_uint16(f)
        py_len = read_uint16(f)
        py_str = read_utf16_str(f, -1, py_len)

        if py_idx not in py_map:
            py_map[py_idx] = py_str

        # 如果拼音为 zuo，说明是最后一个了
        if py_str == 'zuo':
            break
    return py_map


def get_records(f, file_size, hz_offset, py_map):
    f.seek(hz_offset)
    records = []
    while f.tell() != file_size:
        word_count = read_uint16(f)
        py_idx_count = int(read_uint16(f) / 2)

        py_set = []
        for i in range(py_idx_count):
            py_idx = read_uint16(f)
            if (py_map.get(py_idx, None) == None):
                return records
            py_set.append(py_map[py_idx])
        py_str = " ".join(py_set)

        for i in range(word_count):
            word_len = read_uint16(f)
            word_str = read_utf16_str(f, -1, word_len)

            # 跳过 ext_len 和 ext 共 12 个字节
            f.read(12)
            records.append((py_str, word_str))
    return records


def get_words_from_sogou_cell_dict(fname):
    with open(fname, 'rb') as f:
        hz_offset = get_hz_offset(f)

        (title, category, desc, samples) = get_dict_meta(f)
        #print("title: %s\ncategory: %s\ndesc: %s\nsamples: %s" %
        #      (title, category, desc, samples))

        py_map = get_py_map(f)

        file_size = os.path.getsize(fname)
        words = get_records(f, file_size, hz_offset, py_map)
        return words


def save(records, f):
    records_translated = list(map(lambda x: "%s\t%s" % (
        x[1], x[0]), records))
    f.write("\n".join(records_translated))
    return records_translated

def downloadDict():
    with open("config.json") as config:
        list = json.load(config)
        for conf in list:
            url = conf.get("url")
            name = conf.get("name")
            print("下载词库：%s" % name)
            f = urllib.request.urlopen(url + "&name=" + urllib.parse.quote(name))
            with open("scel/%s.scel" % name, "wb") as scel:
                scel.write(f.read())

def main():
    dict_file_header = """# Rime dictionary
# encoding: utf-8
# Source: %s

---
name: luna_pinyin.%s
version: "%s"
sort: by_weight
use_preset_vocabulary: false
...
"""
    with open("config.json") as config:
        list = json.load(config)
        for conf in list:
            url = conf.get("url")
            name = conf.get("name")
            dictName = conf.get("dictName")
            print("下载词库：%s" % name)
            f = urllib.request.urlopen(url + "&name=" + urllib.parse.quote(name))
            scel_file = "%s.scel" % name
            with open("scel/%s.scel" % name, "wb") as scel:
                scel.write(f.read())
            dict_file = "luna_pinyin.%s.dict.yaml" % dictName
            dict_file_content = []
            dict_file_content.append(dict_file_header % (url, dictName, datetime.datetime.now().strftime("%Y.%m.%d")))
            records = get_words_from_sogou_cell_dict(os.path.join("./scel", scel_file))
            print("%s: %s 个词" % (scel_file, len(records)))
            with open(os.path.join("./out", scel_file.replace(".scel", ".txt")), "w") as fout:
                dict_file_content.extend(save(records, fout))
            with open(os.path.join("./out", dict_file), "w") as dictfout:
                dictfout.write("\n".join(dict_file_content))
            print("-"*80)

if __name__ == "__main__":
    main()
