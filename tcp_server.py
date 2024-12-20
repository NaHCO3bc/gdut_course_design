import socket
import mysql.connector
import json
from datetime import datetime
from math import sin, cos

# 连接 MySQL 数据库
def get_db_connection():
    connection = mysql.connector.connect(
        host='localhost',       
        user='debian-sys-maint',    
        password='SkrcGTjcUD720PCb',       
        database='pose'       
    )
    return connection

# 自定义 JSON 编码器，处理 datetime 类型
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()  # 将 datetime 转换为 ISO 格式字符串
        return super().default(obj)

# 从 MySQL 数据库获取所有的位置信息和姿态数据
def fetch_pose_data():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM pose_data ORDER BY id DESC LIMIT 1;")  # 获取所有数据，按 ID 升序排列
    row = cursor.fetchone()
    cursor.close()
    connection.close()
    
    if row:
        pose_data = {
            'position': {'x': row[1], 'y': row[2], 'z': row[3]},
            'orientation': {'x': row[4], 'y': row[5], 'z': row[6], 'w': row[7]},
            'timestamp': row[8]  # 添加时间戳
        }
        return pose_data
    return None

# 使用航位推算计算轨迹
def dead_reckoning(prev_pose, current_pose):
    delta_x = current_pose['position']['x'] - prev_pose['position']['x']
    delta_y = current_pose['position']['y'] - prev_pose['position']['y']
    delta_theta = 2 * sin(current_pose['orientation']['z'])  # 使用z轴旋转角度

    new_x = prev_pose['position']['x'] + (delta_x * cos(delta_theta) - delta_y * sin(delta_theta))
    new_y = prev_pose['position']['y'] + (delta_x * sin(delta_theta) + delta_y * cos(delta_theta))
    new_theta = prev_pose['orientation']['z'] + delta_theta

    return new_x, new_y, new_theta

# def dead_reckoning(prev_pose, velocity, angular_velocity, delta_t):
#     # 提取前一时刻的位置和方向
#     x_prev = prev_pose['position']['x']
#     y_prev = prev_pose['position']['y']
#     theta_prev = prev_pose['orientation']['theta']  # 小车的偏航角（方向）
    
#     # 计算当前时刻的距离增量（速度 * 时间）
#     delta_distance = velocity * delta_t
    
#     # 计算新的位置
#     new_x = x_prev + delta_distance * cos(theta_prev)
#     new_y = y_prev + delta_distance * sin(theta_prev)
    
#     # 计算新的方向（角度）通过角速度积分
#     new_theta = theta_prev + angular_velocity * delta_t

#     return new_x, new_y, new_theta

# 定义 JSON HTTP 响应
def http_response(data):
    response = 'HTTP/1.1 200 OK\r\n'
    response += 'Content-Type: application/json\r\n'
    response += 'Access-Control-Allow-Origin: *\r\n'  # 允许跨域请求
    response += 'Content-Length: {}\r\n\r\n'.format(len(data))
    response += data
    return response

# 处理 favicon 请求
def favicon_response():
    response = 'HTTP/1.1 404 NOT FOUND\r\n'
    response += 'Content-Type: text/plain\r\n\r\n'
    response += '404 Not Found'
    return response

# 处理 HTML 文件请求
def html_response():
    try:
        with open('index.html', 'r', encoding='utf-8') as file:
            html_content = file.read()
        response = 'HTTP/1.1 200 OK\r\n'
        response += 'Content-Type: text/html; charset=utf-8\r\n'
        response += 'Content-Length: {}\r\n\r\n'.format(len(html_content.encode('utf-8')))
        response += html_content
    except FileNotFoundError:
        response = 'HTTP/1.1 404 NOT FOUND\r\n'
        response += 'Content-Type: text/html\r\n'
        response += 'Content-Length: 39\r\n\r\n'
        response += '404 Not Found: The requested file was not found on the server.'
    return response

# 设置 TCP HTTP 服务器
def tcp_http_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('0.0.0.0', 8080))  # 监听所有接口，使用端口8080
    server_socket.listen(5)
    print('HTTP Server is running...')

    prev_pose = None  # 用于存储上一个位置信息，初始化为 None

    while True:
        client_socket, addr = server_socket.accept()
        print(f'Connection from {addr}')
        
        # 读取客户端的 HTTP 请求
        request = b""
        while True:
            chunk = client_socket.recv(1024)
            request += chunk
            if len(chunk) < 1024:
                break

        request_str = request.decode('utf-8')
        print(f"Request: {request_str}")

        # 处理 favicon 请求，避免错误
        if 'GET /favicon.ico' in request_str:
            response = favicon_response()
            client_socket.sendall(response.encode('utf-8'))

        elif 'GET /data' in request_str:
            # 获取MySQL 数据
            current_pose = fetch_pose_data()

            # 如果有之前的位置信息，计算轨迹
            if current_pose:
                if prev_pose:
                    new_x, new_y, new_theta = dead_reckoning(prev_pose, current_pose)
                    trajectory = {
                        'x': new_x,
                        'y': new_y,
                        'theta': new_theta
                    }
                else:
                    trajectory = {
                        'x': current_pose['position']['x'],
                        'y': current_pose['position']['y'],
                        'theta': current_pose['orientation']['z']
                    }

                prev_pose = current_pose  # 更新上一帧数据

                # 构造响应数据，包含所有 pose 数据和计算的轨迹
                response_data = {
                    'pose_data': current_pose,  # 原始的 pose 数据
                    'trajectory': trajectory    # 计算的轨迹数据
                }

                # 发送 HTTP 响应
                response = http_response(json.dumps(response_data, cls=DateTimeEncoder))
                client_socket.sendall(response.encode('utf-8'))

        elif 'GET /' in request_str:  # 处理根路径请求，返回 HTML 文件
            response = html_response()
            client_socket.sendall(response.encode('utf-8'))

        else:
            # 处理其他请求
            response = 'HTTP/1.1 404 NOT FOUND\r\n'
            response += 'Content-Type: text/plain\r\n\r\n'
            response += '404 Not Found'
            client_socket.sendall(response.encode('utf-8'))

        client_socket.close()

if __name__ == '__main__':
    tcp_http_server()
