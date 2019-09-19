import socket
import json
from pymongo import MongoClient
import os
import struct
import hashlib
import _thread

# 创建监听用socket绑定端口
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
host = '127.0.0.1'
port = 8080
s.bind((host, port))
s.listen(5)
print('正在监听：', host, ':', port)


# 连接用户名密码数据库
conn = MongoClient('127.0.0.1', 27017)
if not conn:
    print('mongodb连接失败')
# 连接my_socket_server_db数据库，没有则自动创建
db = conn.my_socket_server_db
# 使用logindb集合，没有则自动创建
logindb = db.logindb


if not os.path.exists('serverfiles'):
    os.mkdir('serverfiles')
    print('存放文件的文件夹已创建')


# 取hash值存入数据库以提高安全性
def psword_hash(cmds):
    userdata={
        "username": cmds[1],
        "password": cmds[2]
    }
    print('#')
    s=json.dumps(userdata).encode()
    psword_HASH = hashlib.md5(s).hexdigest() #md5码哈希别用内置哈希函数
    return psword_HASH

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

# 登录
def login(c,userNow,cmds):
    psword_HASH = psword_hash(cmds)
    response_message = ''
    username = cmds[1]
    if not userNow == '':
        response_message='用户<{}>: 您已成功登录，如需重新登录请先注销\r\n'.format(userNow)
    elif logindb.count_documents({'username': username}) == 1 and logindb.find_one({'username': username})['password'] == psword_HASH:
        userNow=username
        response_message='登录成功\r\n欢迎您，用户<{}>:)\r\n'.format(userNow)
    else:
        response_message='登录失败，请确认用户名和密码:(\r\n'
    sendMsg(c,response_message)
    return userNow

# 注册
def register(c,userNow,cmds):
    psword_HASH = psword_hash(cmds)
    response_message = ''
    username = cmds[1]

    if logindb.count_documents({'username': username}) == 0:
        logindb.insert_one({
            'username':username,
            'password':psword_HASH
            })
        userNow=username
        response_message='注册成功，已自动登录\r\n欢迎您，用户<{}>XD\r\n'.format(userNow)
    else:
        response_message='注册失败：此用户已存在:(\r\n'
    sendMsg(c,response_message)
    return userNow

# 注销
def logout(c,userNow,cmds):
    if not userNow == '':
        response_message='用户<{}>,您已安全退出XD\r\n欢迎再次使用\r\n'.format(userNow)
        userNow = ''
    else:
        response_message='登录后才可以正常使用注销操作'
    sendMsg(c,response_message)
    return userNow

# TODO: 列出目录文件(类似ftp命令行)
def listDir(c,userNow,cmds):
    files = os.listdir('serverfiles')
    response_message = ''
    for i in files:
        response_message += i +'\r\n'
    sendMsg(c,response_message)

# TODO: 删除文件(类似ftp命令行)
def deleteFiles(c,userNow,cmds):
    dirs = os.getcwd()
    response_message = ''
    for i in range(1, len(cmds)) :
        filePath = os.path.join(dirs,'serverfiles',cmds[i])
        if os.path.exists(filePath):
            os.remove(filePath)
            response_message += '已成功删除 ' + cmds[i] + '\r\n'
        else:
            response_message += '服务器不存在文件 ' + cmds[i] + '\r\n'
    sendMsg(c,response_message)

# (已测试)下载(类似ftp命令行)(有特殊的回应机制)
def downland(c,userNow,cmds):
    dirs = os.getcwd()
    filePath = os.path.join(dirs,'serverfiles',cmds[1])
    fileName = cmds[1]
    if os.path.exists(filePath):
        sendMsg(c,'YES')
        # 这里需要客户端做是否成功的判断（服务器存在文件，可以开始传送）
        headerDic = {
            'filename': fileName,
            'filesize': os.path.getsize(filePath)
        }
        headerBytes = json.dumps(headerDic).encode() 
        c.sendall(struct.pack('i', len(headerBytes)))#发报头长度，这个包固定长度4
        c.sendall(headerBytes) #发报头
        with open(filePath, 'rb') as f:
            for a in f:
                c.sendall(a)
        # 看 https://www.cnblogs.com/Xanderzyl/p/10735247.html 优化之后的版本
    else:
        sendMsg(c,'NO')
        # 这里需要客户端做是否成功的判断

# (已测试)上传(类似ftp命令行)(有特殊的回应机制)
def upload(c,cmds):
    #客户端在发送put命令之前要注意检查是否存在这个文件，服务端不做确认
    dirs = os.getcwd()
    filePath = os.path.join(dirs,'serverfiles',cmds[1])
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
            #计算上传的百分比
            recvPrecent = recvSize*100//totalSize
            # c.sendall(struct.pack('i', recvPrecent))#发百分比，这个包固定长度4
            print('文件{} 总大小：{}  已经上传大小：{}'.format(fileName,totalSize, recvSize))


def connect(c,addr):
    print('Connection Address：', addr)
    sendMsg(c,'欢迎! 使用 "help" 命令查看帮助手册.\r\n')
    # print(clientData)

    # 记录当前登入的用户,为空代表未登录
    userNow = ''
    
    # 标志是否退出
    cmdKeep = True
    while cmdKeep:
        cmds = recvMsg(c).split(' ')
        # 这里接收命令get put dir del bye login logout register
        # 客户端请不要主动断开，请发送bye来让服务器断开连接
        # 请客户端做好发送的命令的检查比如是否是合法文件名等
        # get text.txt
        if cmds[0] == 'login':
            userNow = login(c,userNow,cmds)
            #login命令发送格式：login username password
            #中间用一个空格分开
        elif cmds[0] == 'register':
            userNow = register(c,userNow,cmds)
            #register命令发送格式：register username password
            #中间用一个空格分开
        elif cmds[0] == 'logout':
            userNow = logout(c,userNow,cmds)
            #格式: logout
        elif cmds[0] == 'dir':
            if userNow == '':
                sendMsg(c,'未登录，无法使用文件服务\r\n')
                continue
            listDir(c,userNow,cmds)
            #格式: dir
        elif cmds[0] == 'del':
            if userNow == '':
                sendMsg(c,'未登录，无法使用文件服务\r\n')
                continue
            deleteFiles(c,userNow,cmds)
            #格式: del file1 file2 ... fileN
            #最少一个文件
        elif cmds[0] == 'get':
            if userNow == '':
                sendMsg(c,'未登录，无法使用文件服务\r\n')
                continue
            downland(c,userNow,cmds)
            #格式: get file
            #只支持一个文件，多文件在写了.jpg
        elif cmds[0] == 'put':
            if userNow == '':
                sendMsg(c,'未登录，无法使用文件服务\r\n')
                continue
            upload(c,cmds)
            #格式: put file
        elif cmds[0] == 'bye':
            sendMsg(c,'bye\r\n')
            cmdKeep = False
        else:
            cmdKeep = False     


while True:
    try:
        (c, addr) = s.accept()
        _thread.start_new_thread (connect,(c,addr))
    except Exception as e:
        print(e)

