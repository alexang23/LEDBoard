from threading import Thread
from time import sleep
import time
# from datetime import datetime

import collections
import re
import traceback
# from models.server import Server
# from database import get_db

#from global_variables import alarm_queue, logger
#from global_variables import logger
from global_log import LoggerFile

# import requests
import json
# from fastapi.encoders import jsonable_encoder
from config import settings
from datetime import datetime

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
import sys
import schedule

#### test OK version

# ## MQTT v5 add 1 parameter compare to MQTT v3xx
# def on_connect(thread, mqttc, obj, flags, rc):
#     print("########## connect rc: " + str(rc))
    
# def on_connect_fail(mqttc, userdata):
#     print("########## on_connect_fail: " + str(userdata))

# def on_message(mqttc, obj, msg):
#     print("########## " + msg.topic + " " + str(msg.qos) + " " + str(msg.payload))

# def on_publish(mqttc, obj, mid):
#     print("########## mid: " + str(mid))

# ## MQTT v5 add 1 parameter compare to MQTT v3xx
# def on_subscribe(thread, mqttc, obj, mid, granted_qos):
#     print("########## Subscribed: " + str(mid) + " " + str(granted_qos))

# def on_log(mqttc, obj, level, string):
#     print("########## on_log : " + string)


class MQTTSvc(Thread):
    __instance=None

    @staticmethod
    def getInstance():

        if MQTTSvc.__instance==None:
            MQTTSvc()

        return MQTTSvc.__instance
    
    # # Expected signature for MQTT v3.1 and v3.1.1 is:
    # def on_connect(self, client, userdata, flags, rc):
    #     print("########## connect rc: " + str(rc))
    #     pass

    # for MQTT v5.0:
    def on_connect(self, client, userdata, connect_flags, reason_code, properties):
        try:
            # self.logger.info(f"mqtt : on_connect {reason_code}, session = {connect_flags['session present']}, client_id = {properties.AssignedClientIdentifier}")
            self.logger.info(f"mqtt : on_connect : reason_code={str(reason_code)}, client_id={properties.AssignedClientIdentifier}, connect_flags={str(connect_flags)}")
            # print(client)
            # print(userdata)
            # print(flags)
            # print(reasonCode)
            # print(properties)
        except Exception as err:
            # print(str(err))
            self.logger.error(f"mqtt : on_connect : {str(err)}")

        self.startup_connect = 3
        self.connect = True

    ## MQTT v5 add 1 parameter compare to MQTT v3xx
    # def on_connect(self, thread, mqttc, obj, flags, rc):
    #     print("########## connect rc: " + str(rc))
        
    def on_connect_fail(self, client, userdata):
        try:
            self.logger.info(f"mqtt : on_connect_fail : client={str(client)}, userdata={str(userdata)}")
            # print(client)
            # print(userdata)
        except Exception as err:
            # print(str(err))
            self.logger.error(f"mqtt : on_connect_fail : {str(err)}")

        self.connect = False

    # # Expected signature for MQTT v3.1.1 and v3.1 is:
    # def on_disconnect(self, client, userdata, rc):
    #     print("########## on_disconnect: " + str(rc))
    #     pass

    # for MQTT v5.0:
    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        try:
            self.logger.info(f"mqtt : on_disconnect : client={str(client)}, userdata={str(userdata)}, disconnect_flags={str(disconnect_flags)}, reason_code={str(reason_code)}, properties={str(properties)}")
            # print(client)
            # print(userdata)
            # print(reasonCode)
            # print(properties)
        except Exception as err:
            # print(str(err))
            self.logger.error(f"mqtt : on_disconnect : {str(err)}")
        self.connect = False

    def on_message(self, client, userdata, msg):
        # print("########## " + msg.topic + " " + str(msg.qos) + " " + str(msg.payload))
        try:
            if msg.topic.endswith("Process"):
                self.logger.info(f"mqtt : on_message topic={msg.topic}, qos={str(msg.qos)}, data={str(msg.payload)}")
                if settings.CLAMP_ENABLE:
                    payload = json.loads(msg.payload)

                    portno = payload['port_no']
                    if portno not in self.controller.loadport:
                        self.logger.warning('mqtt : {}/Process port_no {} is not exist.'.format(settings.MQTT_TOPIC_SERVER, portno))
                        return
                
                    if self.controller.loadport[portno]['com'] == 'e84':
                        id = self.controller.loadport[portno]['id']
                
                        if payload['process_state'] == settings.CLAMP_ON:
                            # payload['dual_port']
                            self.controller.e84[id].run_cmd('clamp_on')
                            self.logger.info(f"mqtt : port_no={portno}, process_state={payload['process_state']}, CLAMP_ON")
                        elif payload['process_state'] == settings.CLAMP_OFF:
                            self.controller.e84[id].run_cmd('clamp_off')
                            self.logger.info(f"mqtt : port_no={portno}, process_state={payload['process_state']}, CLAMP_OFF")
                    else:
                        self.logger.warning('mqtt : {}/Process port_no {} is not a E84 controller.'.format(settings.MQTT_TOPIC_SERVER, portno))
            
            elif msg.topic.endswith("IPC"):
                # self.logger.info(f"mqtt : on_message topic={msg.topic}, qos={msg.qos}, state={msg.state}, retain={msg.retain}, data={str(msg.payload.decode())}")
                self.logger.info(f"mqtt : on_message topic={msg.topic}, qos={msg.qos}, state={msg.state}, retain={msg.retain}, data={str(msg.payload)}")
                if msg.retain:
                    return
                payload = json.loads(msg.payload)

                if 'type' in payload:
                    if payload['type'] in [1, 3, 5]:
                        self.logger.info(f"######## exclude ########")
                        return
                    
                if payload['type'] == 2 or payload['type'] == 4: # Place & Go message
                    pass
                elif payload['type'] == 3: # Equipment message
                    # if settings.LEDBOARD2_ENABLE:
                    #     self.controller.device2.on_notify(payload)
                    # else:
                    #     self.controller.device.on_notify(payload)
                    # return
                    pass
                else:
                    port_no = payload['port_no']

                    if self.eqp_state[port_no] != payload['eqp_state']:
                        self.eqp_state[port_no] = payload['eqp_state']
                        self.logger.info(f">>>>>>>> mqtt : port_no={port_no}, eqp_state changed to {payload['eqp_state']} <<<<<<<<")
                        copy_payload = payload.copy()
                        copy_payload['type'] = 3
                        if settings.LEDBOARD2_ENABLE:
                            if copy_payload['port_no'] < 3:
                                self.controller.device.on_notify(copy_payload)
                            else:
                                self.controller.device2.on_notify(copy_payload)
                        else:
                            self.controller.device.on_notify(copy_payload)
                    
                    if payload['type'] == 0 and payload['stream'] == 6 and payload['function'] == 11 and payload['code_id'] == 0 and payload['sub_id'] == 0:
                        self.logger.info(f"######## exclude ########")
                        return
                    if payload['type'] == 0 and payload['stream'] == -1 and payload['function'] == -1 and payload['code_id'] == 0:
                        self.logger.info(f"######## exclude ########")
                        return
                    if payload['code_id'] == 0x0071:
                        if payload['mode'] == 2:
                            self.logger.info(f"######## exclude ########")
                            return
                        if payload['sub_id'] not in [0, 1, 2, 3, 4, 5, 6, 7, 20, 21, 22, 23, 24, 25]:
                            self.logger.info(f"######## exclude ########")
                            return
                    elif payload['code_id'] not in [0, 0x8003, 0x0080, 0x001c]:
                        self.logger.info(f"######## exclude ########")
                        return
                # self.logger.info(f"mqtt : on_message topic={msg.topic}, qos={msg.qos}, state={msg.state}, retain={msg.retain}, data={str(msg.payload)}")
                if settings.LEDBOARD2_ENABLE:
                    if payload['port_no'] < 3:
                        self.controller.device.on_notify(payload)
                    else:
                        self.controller.device2.on_notify(payload)
                else:
                    self.controller.device.on_notify(payload)
            elif msg.topic.endswith("response"):
                self.logger.info(f"mqtt : on_message topic={msg.topic}, qos={str(msg.qos)}, data={str(msg.payload)}")
                payload = json.loads(msg.payload)
                if settings.LEDBOARD2_ENABLE:
                    if payload['port_no'] < 3:
                        self.controller.device.on_notify(payload)
                    else:
                        self.controller.device2.on_notify(payload)
                else:
                    self.controller.device.on_notify(payload)
                    
            # elif msg.topic.endswith("Server"):
            #     self.logger.info(f"mqtt : on_message topic={msg.topic}, qos={str(msg.qos)}, data={str(msg.payload)}")
            elif msg.topic.endswith("Request"):
                # Get the response properties, abort if they're not given
                props = msg.properties
                if not hasattr(props, 'ResponseTopic') or not hasattr(props, 'CorrelationData'):
                    self.logger.warning("No reply requested")
                    return

                corr_id = props.CorrelationData
                reply_to = props.ResponseTopic
                payload = json.loads(msg.payload)
                self.logger.info(f"corr_id={corr_id}, reply_to={reply_to}, payload={payload}")
                if ('cmd' in payload) and ('port_no' in payload):
                    port_no = payload['port_no']
                    # self.uiform.e84[port_no].api_request(payload['cmd'], payload['data'], payload['correlation'])
                    self.uiform.e84[port_no].api_request(payload['cmd'], payload['data'], props)
        except Exception as err:
            self.logger.error(f"mqtt : on_message : {str(err)}")

    def on_publish(self, client, userdata, mid, reason_code, properties):
        # print("########## mid: " + str(mid))
        pass

    # # Expected signature for MQTT v3.1.1 and v3.1 is:
    # def on_subscribe(self, client, userdata, mid, granted_qos):
    #     print("########## Subscribed: " + str(mid) + " " + str(granted_qos))

    # for MQTT v5.0:
    def on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        try:
            # self.logger.info("########## Subscribed: " + str(mid) + " " + str(properties))
            # self.logger.info(f"mqtt : on_subscribe mid = {mid}, reason_code_list = {str(reason_code_list)}")
            self.logger.info(f"mqtt : on_subscribe : mid={mid}")
            # print(client)
            # print(userdata)
            # print(mid)
            # print(reasonCodes)
            # print(properties)
        except Exception as err:
            # print(str(err))
            self.logger.error(f"mqtt : on_subscribe : {str(err)}")

    # ## MQTT v5 add 1 parameter compare to MQTT v3xx
    # def on_subscribe(self, thread, mqttc, obj, mid, granted_qos):
    #     print("########## Subscribed: " + str(mid) + " " + str(granted_qos))

    # # Expected signature for MQTT v3.1.1 and v3.1 is:
    # def on_unsubscribe(self, client, userdata, mid):
    #     pass

    # for MQTT v5.0:
    def on_unsubscribe(self, client, userdata, mid, reason_code_list, properties):
        try:
            self.logger.info(f"mqtt : on_unsubscribe : mid={mid}, reason_code_list={str(reason_code_list)}, properties={str(properties)}")
            # print(client)
            # print(userdata)
            # print(mid)
            # print(reasonCodes)
            # print(properties)
        except Exception as err:
            # print(str(err))
            self.logger.error(f"mqtt : on_unsubscribe : {str(err)}")

    def on_log(self, client, userdata, level, buf):
        # print("########## on_log : " + buf)
        pass

    def __init__(self, controller, logger, uiform=None) -> None:
        super().__init__(name="MQTTSvc")
        MQTTSvc.__instance=self
        self.name = "MQTTSvcs"
        self.svc_name = 'mqtt'
        self.stop = False
        self.uiform = uiform
        self.controller = controller
        self.logger = logger
        self.logger_heartbeat = LoggerFile("heartbeat", "heartbeat.log")
        self.logger_mqtt = LoggerFile("mqtt", "mqtt.log")
        self.receive_queue = collections.deque()
        # self.alarms = {}
        self.svr_enable = settings.MQTT_ENABLE
        self.ip = settings.MQTT_IP
        self.port = settings.MQTT_PORT
        self.device_id = settings.DEVICE_ID
        self.client_id = settings.MQTT_CLIENT_ID
        self.topic = settings.MQTT_TOPIC
        self.topic_server = settings.MQTT_TOPIC_SERVER
        self.heartbeat_enable = settings.MQTT_HEARTBEAT_ENABLE
        self.heartbeat_time = settings.MQTT_HEARTBEAT_TIME
        self.mqttc = None
        self.eqp_state = [-1, -1, -1, -1]  # for 4 ports
        self.startup_connect = 0
        self.connect = False

        Thread.__init__(self)
        self.setDaemon(True)
        self.start()

    def connect_MQTT_service(self):
        try:
            # MQTT_ENABLE=1
            # MQTT_IP='192.168.0.235'
            # MQTT_PORT=1883
            # MQTT_CLIENT_ID='E847-IPC-Full'
            # MQTT_TOPIC='IPC'

            # self.mqttc = mqtt.Client(self.client_id) # not for MQTT
            # self.mqttc = mqtt.Client(client_id=self.client_id, protocol=settings.MQTT_PROTOCOL, transport=settings.MQTT_TRANSPORT) # MQTT 5.0
            self.mqttc = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, protocol=settings.MQTT_PROTOCOL, transport=settings.MQTT_TRANSPORT)
            # self.mqttc = mqtt.Client(self.client_id, clean_session=settings.MQTT_CLEAN_SESSION, protocol=settings.MQTT_PROTOCOL, transport=settings.MQTT_TRANSPORT) # Not MQTT 5.0
            # mqttc = mqtt.Client(args.clientid, clean_session = not args.disable_clean_session, transport='websockets')
            self.mqttc.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
            
            # self.mqttc.on_message = on_message
            # self.mqttc.on_connect = on_connect
            # self.mqttc.on_publish = on_publish
            # self.mqttc.on_subscribe = on_subscribe
            # self.mqttc.on_connect_fail = on_connect_fail
            # self.mqttc.on_log = on_log

            self.mqttc.on_message = self.on_message
            self.mqttc.on_connect = self.on_connect
            self.mqttc.on_publish = self.on_publish
            self.mqttc.on_subscribe = self.on_subscribe
            self.mqttc.on_unsubscribe = self.on_unsubscribe
            self.mqttc.on_disconnect = self.on_disconnect
            self.mqttc.on_connect_fail = self.on_connect_fail
            self.mqttc.on_log = self.on_log
            
            self.logger.info("mqtt : connecting to "+self.ip+" port:"+str(self.port))
            # self.mqttc.connect(host=self.ip, port=self.port, keepalive=settings.MQTT_KEEPALIVE, clean_start=settings.MQTT_CLEAN_START_FIRST_ONLY)
            self.mqttc.connect(host=self.ip, port=self.port, clean_start=True)
            self.mqttc.subscribe(settings.MQTT_TOPIC, settings.MQTT_QOS)
            # self.mqttc.subscribe(settings.MQTT_TOPIC+'/Request', settings.MQTT_QOS)
            self.mqttc.subscribe(settings.MQTT_TOPIC_SERVER, settings.MQTT_QOS)
            self.mqttc.subscribe(settings.MQTT_TOPIC_SERVER+'/Process', settings.MQTT_QOS)
            self.mqttc.subscribe(settings.MQTT_TOPIC_SERVER+'/LRC/response', settings.MQTT_QOS)
            self.mqttc.subscribe(settings.MQTT_TOPIC_SERVER+'/WIP/response', settings.MQTT_QOS)
            self.mqttc.loop_start()
            
            
            # db = next(get_db())
            # webapi_server = db.query(Server).filter(Server.name == 'WebAPI Server').first()
            
            # if webapi_server :
            #     self.ip = webapi_server.ip
            #     self.port = webapi_server.port
            #     self.url = webapi_server.url
            #     self.svr_enable = webapi_server.svr_enable



            return True

        except Exception as err:
            self.logger.error(f"mqtt : connect_MQTT_service : {str(err)}")
            return False
        
    # def enable_webapi(self, set):
    #     self.svr_enable = set
    #     self.logger.info('WebAPI Server enable = {}'.format(set))
        
    # def update_webapi(self, ip, port, url):
    #     if self.ip != ip :
    #         self.logger.info('WebAPI Server IP change from {} to {}.'.format(self.ip, ip))
    #         self.ip = ip
    #     if self.port != port :
    #         self.logger.info('WebAPI Server Port change from {} to {}.'.format(self.port, port))
    #         self.port = port
    #     if self.url != url :
    #         self.logger.info('WebAPI Server URL change from {} to {}.'.format(self.url, url))
    #         self.url = url

    def on_notify(self, data):
        self.receive_queue.append(data)
        #logger.debug('{}'.format(data))
        
    # def superuser_login(self, data):
    #     message = {}
    #     message['userid'] = "gyro"
    #     message['password'] = "gsi5613686"

    #     response = {}
    #     response['result'] = 'NG'
    
    #     res = None
    #     # ipc_ip = data['params']['ip']
    #     # api_port = data['params']['api_port']
    #     try:
    #         res = requests.post('http://{}:{}/api/auth/login'.format(self.ip, self.port), json=message, timeout=5)
    #     except requests.ConnectionError:
    #         self.logger.error('webapi_svc.py superuser_login error : requests.ConnectionError')
    #         response['status_code'] = 503
    #         response['reason'] = 'requests.ConnectionError'
    #         return response
    #     except requests.Timeout:
    #         self.logger.error('webapi_svc.py superuser_login error : requests.Timeout')
    #         response['status_code'] = 408
    #         response['reason'] = 'requests.Timeout'
    #         return response
    #     except Exception as err:
    #         self.logger.error('webapi_svc.py superuser_login error : {}'.format(str(err)))
    #         response['status_code'] = 400
    #         response['reason'] = str(err)
    #         return response
        
    #     #print('requests.post : [{}] {}'.format(res.status_code, res.text))
    #     response['status_code'] = res.status_code
    #     response['reason'] = res.reason
    #     #print(response)
        
    #     if res.status_code == 200 :
    #         response['result'] = 'success'
    #         response['access_token'] = json.loads(res.text)['access_token']
    #         #print(access_token)

    #     return response

    def publish(self, data):
        try:
            if not self.mqttc:
                return False
            
            if 'Server' in data: # publish to Server
                payload = json.dumps(data)
                if not self.connect:
                    return False
                if settings.MQTT_DEBUG_ENABLE:
                    print(f"[Server]:{payload}")
                self.logger_mqtt.info(f"[Server]:{payload}")
                infot = self.mqttc.publish(f"{settings.MQTT_TOPIC_SERVER}", payload, qos=settings.MQTT_QOS)
                # infot = self.mqttc.publish(self.topic, payload, qos=settings.MQTT_QOS)
                # infot.wait_for_publish(5)
                # del data['device_id']
            
            else: # publish to IPC
                if self.mqttc.is_connected():
                    payload = json.dumps(data)
                    if settings.MQTT_DEBUG_ENABLE:
                        print(f"[IPC]:{payload}")
                    self.logger_mqtt.info(f"[IPC]:{payload}")
                    res = self.mqttc.publish(f"{settings.MQTT_TOPIC}/LEDBoard", payload, qos=settings.MQTT_QOS)
                    # print(f'mqtt publish : {payload}')
                    return True
        except Exception as err:
            # print(str(err))
            self.logger.error('Mqtt Proxy : {}'.format(str(err)))
            return False
        return False

    def data_process(self, data):
        try:
            
            # print(data)
            # self.mqtt.publish(settings.MQTT_TOPIC, data)
            
            tmp = datetime.now().strftime('%Y-%m-%d %H:%M:%S %f')[:-3]
            # msg_txt = f"########## {tmp} : {str(data)}"
            # msg_txt = data
            # msg_txt = str(data) ## python dictionary format which using single quotes
            msg_txt = str(data).replace("'",'"') ## json format which using double quotes
            # print(f"########## Publishing: {tmp} {msg_txt}")

            if 'cmd' in data:
                props = mqtt.Properties(PacketTypes.PUBLISH)
                props.CorrelationData = data['correlation'].CorrelationData
                reply_to = data['correlation'].ResponseTopic
                del data['correlation']
                payload = json.dumps(data)
                print("Sending response "+str(data['result'])+" on '" + reply_to + "': "+str(props.CorrelationData))
                if not self.connect:
                    return False
                # infot = self.mqttc.publish(self.topic+'/Response', msg_txt, qos=settings.MQTT_QOS)
                # infot = self.mqttc.publish(self.topic+'/Response', msg_txt, qos=settings.MQTT_QOS)
                infot = self.mqttc.publish(reply_to, payload, qos=1, properties=props)
                infot.wait_for_publish(5)
                return True
            
            payload = json.dumps(data)
            if 'device_id' in data:
            # if  data['type'] == 0 and \
            #     (   data['code_id'] == 5 or \
            #         data['code_id'] == 113 or \
            #         data['code_id'] >= 128 ):
            
                # msg_txt = str(data).replace("'",'"')
                # infot = self.mqttc.publish(self.topic_server, msg_txt, qos=settings.MQTT_QOS)
                # data2 = data
                # del data2['port_no']
                # del data2['dual_port']
                # del data2['type']
                # del data2['stream']
                # del data2['function']
                # del data2['status']
                # payload = json.dumps(data2)
                if not self.connect:
                    return False
                infot = self.mqttc.publish(self.topic_server, payload, qos=settings.MQTT_QOS)
                # infot.wait_for_publish(5)
                # del data['device_id']

            # infot = self.mqttc.publish(self.topic, msg_txt, qos=settings.MQTT_QOS)
            # payload = json.dumps(data)
            pattern = r'"device_id":\s*".+?",?\s*'
            no_deviceid_payload = re.sub(pattern, '', payload)
            # print(no_deviceid_payload)
            if not self.connect:
                return False
            infot = self.mqttc.publish(self.topic, no_deviceid_payload, qos=settings.MQTT_QOS)
            # infot.wait_for_publish(5)

        except Exception as err:
            self.logger.error(f"mqtt : data_process : {str(err)}")
            return False
    
        return True
        if 'ALARM' in data['class'] or 'EVENT' in data['class']:
            res = None
            
            # response = self.superuser_login(data)
            
            # if response['result'] != 'success' :
            #     return
            
            # header = {}
            # header['Authorization'] = 'Bearer {}'.format(response['access_token'])
            
            #self.logger.debug('requests.post : {}'.format(data))
            try:
                # ipc_ip = data['params']['ip']
                # ipc_port = data['params']['port']
                # api_port = data['params']['api_port']
                # ipc_enable = data['params']['ipc_enable']
                # ftp_enable = data['params']['ftp_enable']
                payload = json.dumps(data)
                # print(payload)
                # url = 'http://{}:{}/api/test{}?payload={}'.format(self.ip, self.port, self.url, payload)
                url = 'http://{}:{}{}'.format(self.ip, self.port, self.url)
                # res = requests.post(url, headers=header, json=payload, timeout=5)
                # res = requests.post(url, headers=header, timeout=5)
                res = requests.post(url, json=payload, timeout=5)
                
            except requests.ConnectionError:
                self.logger.error('requests.ConnectionError : {}'.format(url))
                return
            except requests.Timeout:
                self.logger.error('requests.Timeout : {}'.format(url))
                return
            except:
                self.logger.error(traceback.format_exc())
                return
                
            #self.logger.debug('requests.post : [{}] {}'.format(res.status_code, res.text))
            response = json.loads(res.text)
            response['status_code'] = res.status_code
            response['reason'] = res.reason
            #print(response)
            
            if res.status_code != 200:
                pass
            else:
                pass

    def memory_check(self):
        if not self.svr_enable:
            return
        
        try:
            receive_queue_size = len(self.receive_queue)
            
            stdout_size = sys.getsizeof(sys.stdout)
            
            self.logger.info(f"mqtt : memory_check : receive_queue = {receive_queue_size}, stdout = {stdout_size}")
            # self.logger.info(f"{self.port_id} : stdout = {stdout_size}, logger size = {sys.getsizeof(self.logger)}, logger file = {self.logger.getfilestreamsize()}, logger stream = {self.logger.getstdoutstreamsize()}, logger sql = {self.logger.getsqlstreamsize()}")
        except Exception as err:
            self.logger.error(f"mqtt : memory_check : {str(err)}")

    def heartbeat(self):
        if not self.heartbeat_enable:
            return
        
        try:
            if not self.connect:
                return False
            
            data = {}
            data['device_id'] = self.device_id
            data['type'] = 0
            data['stream'] = 1
            data['function'] = 1
            data['occurred_at'] = time.time()
            
            payload = json.dumps(data)
            
            infot = self.mqttc.publish(self.topic_server, payload, qos=settings.MQTT_QOS)
            
            # self.logger.info(f"mqtt : heartbeat")
            self.logger_heartbeat.info('alive')
        except Exception as err:
            self.logger.error(f"mqtt : heartbeat : {str(err)}")
            
    def run(self):
        
        if settings.MEMORY_CHECK:
            schedule.every(5).minutes.do(self.memory_check)
            
        if self.heartbeat_enable:
            schedule.every(self.heartbeat_time).seconds.do(self.heartbeat)
            
        # self.logger.error('MqttSvc Starting')
        self.connect_MQTT_service()
        
        while not self.stop :
            if self.startup_connect < 3:
                sleep(1)
                self.startup_connect += 1
                continue
            if not self.connect:
                self.connect_MQTT_service()
                sleep(1)
                continue
            while self.receive_queue :
                if not self.connect:
                    break
                data = self.receive_queue.popleft()
                # self.logger.debug('inside webapi_svr run = {}'.format(data))
                # print('inside mqtt_svr run = {}'.format(data))
                if self.svr_enable :
                    if not self.data_process(data):
                        break
            if settings.MEMORY_CHECK:
                schedule.run_pending()
            if self.heartbeat_enable:
                schedule.run_pending()
            sleep(0.1)
            # print('inside mqtt_svr')
            
            
