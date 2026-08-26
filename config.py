# from pydantic-settings import BaseSettings
# from dotenv import load_dotenv

# # Load environment variables from .env file
# load_dotenv()

# class Settings(BaseSettings):
#     # Define the settings with default values
#     app_name: str = "MyApp"
#     debug: bool = False
#     api_key: str

# from pydantic_settings import BaseSettings, SettingsConfigDict

# class Settings(BaseSettings):
#     DB_HOST:str = 'env-db.com'
#     DB_PORT:int = 3306
#     DB_USER:str = 'root'
#     DB_PASS:str = 'mypassword'
#     APP_DEBUG:bool = False
#     LOG_LEVEL:str = 'error'

#     LEDBOARD_RESET:int = 1
#     LEDBOARD_MODE:int = 2
#     LEDBOARD_MANUAL:int = 3
    
#     model_config = SettingsConfigDict(env_file='config.ini', env_file_encoding='utf-8')

# # Create an instance of the Settings class
# # settings = Settings(_env_file='.env', _env_file_encoding='utf-8')
# settings = Settings()

# # Usage Example
# if __name__ == "__main__":
#     try:
#         # Access the settings
#         print(f"DB_HOST: {settings.DB_HOST}")
#         print(f"DB_PORT: {settings.DB_PORT}")
#         print(f"APP_DEBUG: {settings.APP_DEBUG}")
#     except ValueError as e:
#         print(f"Configuration error: {e}")

from pydantic import BaseSettings

class Settings(BaseSettings):
	HOST:str = '0.0.0.0'
	PORT:int = 7009

	AUTH_ENABLE:bool = False
	ACCESS_TOKEN_EXPIRES_IN:int = 180
	REFRESH_TOKEN_EXPIRES_IN:int = 360
	JWT_ALGORITHM:str = 'RS256'

	CLIENT_ORIGIN:str = 'http://localhost:3000'
 
	ENV_FILE_PATH:str = '.env'
	LOG_DIRS:str = 'log'
	E84_GEM300_DIR:str = 'C:\\Users\\Alex\\Downloads\\andrews_4_E84_rfid_20230601_En'
## E84_GEM300_DIR = 'C:\\Users\\EAP\\Downloads\\andrews_dual_E84_rfid_EN-20230327\\andrews_dual_E84_rfid_EN'
#E84_GEM300_DIR = 'C:\\Users\\Alex\\Downloads\\andrews_4_E84_rfid_20230601_En'
	LOG_STDOUT:bool = True
	LOG_SQLITE:bool = True
	LOG_0070:bool = True
	LOG_0071:bool = True
	LOG_LEVEL:int = 20
	# SW_VERSION:str = 'v1.4.0804.0'
	# SW_VERSION:str = 'v1.5.0930.0'
	SW_VERSION:str = 'v1.8.260826.0'

	LEDBOARD_DEBUG_ENABLE:bool = False
	LEDBOARD_ENABLE:bool = True
	LEDBOARD_COM:int = 5
	LEDBOARD_BUTTON_TIME:int = 5
	LEDBOARD_INITIAL:int = 0
	LEDBOARD_RESET:int = 1
	LEDBOARD_MODE:int = 2

	LEDBOARD2_ENABLE:bool = False
	LEDBOARD2_COM:int = 10
 
	CLAMP_ENABLE:bool = False
	CLAMP_ON:int = 1
	CLAMP_OFF:int = 2
	
	CLAMP_TEST:bool = False
	MEMORY_CHECK:bool = False

	log_secs_preserve:int = 90
	log_api_preserve:int = 90
	log_ipc_preserve:int = 90

	JWT_PRIVATE_KEY:str = 'LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlCT2dJQkFBSkJBSSs3QnZUS0FWdHVQYzEzbEFkVk94TlVmcWxzMm1SVmlQWlJyVFpjd3l4RVhVRGpNaFZuCi9KVHRsd3h2a281T0pBQ1k3dVE0T09wODdiM3NOU3ZNd2xNQ0F3RUFBUUpBYm5LaENOQ0dOSFZGaHJPQ0RCU0IKdmZ2ckRWUzVpZXAwd2h2SGlBUEdjeWV6bjd0U2RweUZ0NEU0QTNXT3VQOXhqenNjTFZyb1pzRmVMUWlqT1JhUwp3UUloQU84MWl2b21iVGhjRkltTFZPbU16Vk52TGxWTW02WE5iS3B4bGh4TlpUTmhBaUVBbWRISlpGM3haWFE0Cm15QnNCeEhLQ3JqOTF6bVFxU0E4bHUvT1ZNTDNSak1DSVFEbDJxOUdtN0lMbS85b0EyaCtXdnZabGxZUlJPR3oKT21lV2lEclR5MUxaUVFJZ2ZGYUlaUWxMU0tkWjJvdXF4MHdwOWVEejBEWklLVzVWaSt6czdMZHRDdUVDSUVGYwo3d21VZ3pPblpzbnU1clBsTDJjZldLTGhFbWwrUVFzOCtkMFBGdXlnCi0tLS0tRU5EIFJTQSBQUklWQVRFIEtFWS0tLS0t'
	JWT_PUBLIC_KEY:str = 'LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUZ3d0RRWUpLb1pJaHZjTkFRRUJCUUFEU3dBd1NBSkJBSSs3QnZUS0FWdHVQYzEzbEFkVk94TlVmcWxzMm1SVgppUFpSclRaY3d5eEVYVURqTWhWbi9KVHRsd3h2a281T0pBQ1k3dVE0T09wODdiM3NOU3ZNd2xNQ0F3RUFBUT09Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQ=='

	DEVICE_ID:str ='E84-IPC'
	DEVICE_NAME:str ='E84-IPC'
	LOAD_PORT_NUMBER:int =4

	LOAD_PORT_1_ENABLE:bool = True
	LOAD_PORT_1_COM:int = 1
	LOAD_PORT_1_DUAL:int = 0
	LOAD_PORT_1_RFID:str = 'LF'

	LOAD_PORT_2_ENABLE:bool = True
	LOAD_PORT_2_COM:int = 2
	LOAD_PORT_2_DUAL:int = 0
	LOAD_PORT_2_RFID:str = 'LF'

	LOAD_PORT_3_ENABLE:bool = True
	LOAD_PORT_3_COM:int = 3
	LOAD_PORT_3_DUAL:int = 0
	LOAD_PORT_3_RFID:str = 'UHF'

	LOAD_PORT_4_ENABLE:bool = True
	LOAD_PORT_4_COM:int = 4
	LOAD_PORT_4_DUAL:int = 0
	LOAD_PORT_4_RFID:str = 'UHF'

	RFID_READ_PS_ON:bool = True
	RFID_DEBUG_ENABLE:bool = True

	LF_RFID_ENABLE:bool = True
	LF_RFID_COM:int = 9

	UHF_RFID_ENABLE:bool = False
	UHF_RFID_COM:int = 10

	HSMS_ENABLE:bool = True
	HSMS_IP:str = '127.0.0.1'
	HSMS_PORT:int = 5000
	HSMS_ID:int = 0
	HSMS_NAME:str = 'ABCD01'

	MQTT_DEBUG_ENABLE:bool = False
 
	MQTT_ENABLE:bool = True
	MQTT_IP:str = '127.0.0.1'
	MQTT_PORT:int = 1883
	MQTT_USERNAME:str = 'mcsadmin'
	MQTT_PASSWORD:str = 'gsi5613686'
	MQTT_CLIENT_ID:str = 'ABCD01'
	# MQTT_TOPIC:str = 'MQTT-Ubuntu/IPC'
	# MQTT_TOPIC_SERVER:str = 'MQTT-Ubuntu/Server'
	MQTT_TOPIC:str = 'IPC'
	MQTT_TOPIC_SERVER:str = 'Server'
	MQTT_HEARTBEAT_ENABLE:bool = True
	MQTT_HEARTBEAT_TIME:int = 20

	MQTT_KEEPALIVE:int = 60
	MQTT_QOS:int = 0
	MQTT_CLEAN_SESSION:int = 0
	# MQTT_CLEAN_START=0
	MQTT_CLEAN_START_FIRST_ONLY:int = 3
	MQTT_TRANSPORT:str = 'tcp'
	# MQTT_TRANSPORT:str = 'websockets'
	MQTT_PROTOCOL:int = 5
	# MQTTv31 = 3
	# MQTTv311 = 4
	# MQTTv5 = 5

	FTP_ENABLE:bool = False
	FTP_IP:str = '192.168.0.235'
	FTP_PORT:int = 21
	FTP_CWD:str = '/log/'
	FTP_USERNAME:str = 'admin'
	FTP_PASSWORD:str = 'root1234'
 
	UMC_FAB:str = 'FAB_8S'

	class Config:
		env_file = 'config.ini'
  
settings = Settings()
