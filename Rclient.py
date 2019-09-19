import socket
import json
from pymongo import MongoClient
import os
import struct
import hashlib
import getpass
import time
import re
# 引入正则库来判断文件名是否有效
regex = r'^[^\\/:\*\?"<>\|]+$'

c = socket.socket()  # 创建 socket 对象
host ="127.0.0.1"  # 获取本地主机名
port = 8080  # 设置端口号

# (已测试)防粘包发送，返回发送数据的字节数, 可发送不超过1024字节的数据
def sendMsg(c,msg):
    try:
        msgBytes = msg.encode()
        msgByteSize = len(msgBytes)
        c.sendall(struct.pack('i', msgByteSize))#发长度，这个包固定长度4
        c.sendall(msgBytes)#发msg
        return msgByteSize
    except Exception as e:
        print(e)

# (已测试)防粘包接收，返回接收数据的字节数, 可接收不超过1024字节的数据
def recvMsg(c):
    try:
        byteSize= c.recv(4)
        msgByteSize = struct.unpack('i', byteSize)[0]
        msgBytes = c.recv(msgByteSize)
        msg = msgBytes.decode()
        return msg
    except Exception as e:
        print(e)

# (已测试)客户端下载(类似ftp命令行)(有特殊的回应机制)
def downland(c,cmds):
    #客户端在发送put命令之前要注意检查是否存在这个文件，服务端不做确认
    dirs = os.getcwd()
    filePath = os.path.join(dirs,cmds[1])
    fileName = cmds[1]

    if recvMsg(c)=='NO':
        return

    obj = c.recv(4)#接收报头长度包
    headerSize = struct.unpack('i', obj)[0]

    headerBytes = c.recv(headerSize)# 接收报头
    headerJson = headerBytes.decode()
    headerDic = json.loads(headerJson)
    totalSize = headerDic['filesize']
    
    # 接受真实的数据
    with open(filePath, 'wb') as f:
        recvSize = 0
        while recvSize < totalSize:
            trueSize = min(totalSize-recvSize,1024)
            res = c.recv(trueSize)
            f.write(res)
            recvSize += len(res)
            recvPrecent = recvSize*100//totalSize
            a = '*' * (recvPrecent//10)
            b = '.' * ((100 - recvPrecent)//10)
            print("\r文件{} 已下载{:}%[{}->{}]".format(fileName,recvPrecent,a,b),end="")
    
    print('\n')
    # c.sendall('YES'.encode()) #通知客户端开始发送

# (已测试)客户端下载(类似ftp命令行)(有特殊的回应机制)
def upload(c,cmds):
    dirs = os.getcwd()
    filePath = os.path.join(dirs,cmds[1])
    fileName = cmds[1]
    if os.path.exists(filePath):
        sendMsg(c,'YES')
        totalSize = os.path.getsize(filePath)
        headerDic = {
            'filename': fileName,
            'filesize': os.path.getsize(filePath)
        }
        headerBytes = json.dumps(headerDic).encode() 
        c.sendall(struct.pack('i', len(headerBytes)))#发报头长度，这个包固定长度4
        c.sendall(headerBytes) #发报头
        recvSize = 0
        with open(filePath, 'rb') as f:
            for a in f:
                c.sendall(a)
                #recvPrecentBytes = c.recv(4)
                #recvPrecent = struct.unpack('i', recvPrecentBytes)[0]
                recvSize += len(a)
                recvPrecent = recvSize*100//totalSize
                a = '*' * (recvPrecent//10)
                b = '.' * ((100 - recvPrecent)//10)
                print("\r文件{} 已上传{:}%[{}->{}]".format(fileName,recvPrecent,a,b),end="")
                #print('\r文件{} 总大小：{}  已经上传{}%'.format(fileName,totalSize, recvPrecent),end = " ")
        # 看 https://www.cnblogs.com/Xanderzyl/p/10735247.html 优化之后的版本\
        print('\n')
    else:
        sendMsg(c,'NO')
        print('不存在此文件: {}'.format(fileName))
        # 这里需要客户端做是否成功的判断


def loginRegister(c,cmds):
    if len(cmds)==3 :
        sendMsg(c , ' '.join(cmds))
        print(recvMsg(c))
    if len(cmds)==1 :
        username = input("username:")
        password = getpass.getpass("password:")
        sendMsg(c , cmds[0] +' '+ username +' '+ password)
        print(recvMsg(c))

def logoutDir(c,cmds):
    if len(cmds)==1 :
        sendMsg(c , cmds[0])
        print(recvMsg(c))

def Del(c,cmds):
    if len(cmds)==1 :
        return
    for i in range(1, len(cmds)):
        if not re.match(regex,cmds[i]):
            print('文件名错误！请检查后重新输入')
            return
    sendMsg(c , ' '.join(cmds))
    print(recvMsg(c))

def Bye(c,cmds):
    if len(cmds)==1 :
        sendMsg(c,'bye')
        print(recvMsg(c))
        c.close()
        time.sleep(0.5)
        exit()

def GetPut(c,cmds):
    if len(cmds)==1 :
        return
    for i in range(1, len(cmds)):
        if not re.match(regex,cmds[i]):
            print('文件名错误！请检查后重新输入')
            return
    sendMsg(c , ' '.join(cmds))
    if cmds[0] == 'get':
        downland(c,cmds)
    elif cmds[0] == 'put':
        upload(c,cmds)
        

textHelper = '''
指令

    登录       login 用户名 密码
            或  login  后按提示输入(带密码保护，推荐)
    注册       register 用户名 密码
            或  register  后按提示输入(带密码保护，推荐)

    注销      logout   (不会断开与服务器的连接)
    退出      bye      (断开与服务器的连接并退出程序)


    文件列表   dir    (列出服务器的所有文件)
    删除文件   del 文件1 文件2 ... 文件N
                    （删除文件1到文件N)

    下载      get 文件名    (不支持绝对路径)
    上传      put 文件名    (不支持绝对路径)

    帮助      help

'''


try:
    c.connect((host, port))
    print(recvMsg(c))
    while True:
        cmds = input('>>> ')
        cmds = cmds.split(' ')
        if cmds[0] == 'login':
            loginRegister(c,cmds)
        elif cmds[0] == 'register':
            loginRegister(c,cmds)
        elif cmds[0] == 'logout':
            logoutDir(c,cmds)
        elif cmds[0] == 'dir':
            logoutDir(c,cmds)
        elif cmds[0] == 'del':
            Del(c,cmds)
        elif cmds[0] == 'bye':
            Bye(c,cmds)
        elif cmds[0] == 'get':
            GetPut(c,cmds)
        elif cmds[0] == 'put':
            GetPut(c,cmds)
        if cmds[0] == 'help':
            print(textHelper)
except Exception as e:
    print(e)