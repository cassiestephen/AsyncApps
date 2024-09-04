import asyncio
import argparse
import logging
import time
import re
import aiohttp
import json


logger = logging.getLogger(__name__)

class Server:
    def __init__(self, server_name):
        self.server_name = server_name
        self.port = my_port(self.server_name)
        self.neighbor_list = neighbor_list(self.server_name)
        # saves most recent location message of each client
        self.recent_message = {}

        logging.basicConfig(filename=f'{server_name}.log', level=logging.INFO)

    # based on example from https://docs.python.org/3/library/asyncio-stream.html#examples
    async def handle_echo(self, reader, writer):
        data = await reader.read(10000000)
        message = data.decode()
        addr = writer.get_extra_info('peername')
        print(f"Received {message!r} from {addr!r}")
        logger.info(f"Received {message!r} from {addr!r}")
        if len(message) != 0:
            if message[:2] == "AT":
                flood = self.at(message)
                if (flood == True):
                    await self.flooding(message=message)
            else:
                new_message = message
                if message[:5] == "IAMAT":
                    new_message = self.iamat(message)
                    # update others about this new location
                    await self.flooding(new_message)
                elif message[:7] == "WHATSAT":
                    new_message = await self.whatsat(message) 
                else:
                    logger.info("Bad Message")
                    new_message = f"? {message}"
                logger.info(f"Sending message: {new_message}")

                print(f"Sending message: {new_message!r}")
                writer.write(new_message.encode())
                await writer.drain()

           # print("Close the connection")
            writer.close()
            await writer.wait_closed()

    # based on example from https://docs.python.org/3/library/asyncio-stream.html#examples
    async def main(self):
        server = await asyncio.start_server(self.handle_echo, '127.0.0.1', self.port)

        addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
        print(f'Serving on {addrs}')
        async with server:
            await server.serve_forever()
    
    # server recieves location message from client or neighboring server 
    def iamat(self, message):
        # ex: IAMAT kiwi.cs.ucla.edu +34.068930-118.445127 1621464827.959498503
        message = message.split()
        if len(message) != 4:
            return self.invalid_message(message)
        client = message[1]
        lat_long = message[2]
        msg_time = message[3]

        # valid lat/long?
        if lat_long[0] != '+':
            return self.invalid_message(message)
        if len(re.findall('-', lat_long)) != 1:
            return self.invalid_message(message)
        if len(re.findall('\\.', lat_long)) != 2:
            return self.invalid_message(message)
        if len(re.findall('[^0-9]', lat_long)) != 4:
            return self.invalid_message(message)
        
        # valid time
        if len(re.findall('\\.', msg_time)) != 1:
            return self.invalid_message(message)
        if len(re.findall('[^0-9]', msg_time)) != 1:
            return self.invalid_message(message)
        

        delta_t = time.time() - float(msg_time)
        if (delta_t >= 0):
            delta_t = f"+{delta_t}"
        else:
            delta_t = f"-{delta_t}"

        new_message = f"AT {self.server_name} {delta_t} {client} {lat_long} {msg_time}"
        self.recent_message[client] = new_message.split()
        return new_message

    
    # server recieves message from client asking to retrieve information
    # server uses google nearby places api to return api response using most recent location
    async def whatsat(self, message):
        message = message.split()
        if len(message) != 4:
            return self.invalid_message(message)
        client = message[1]
        rad = message[2]
        info_bound = message[3]

        # error check
        if len(re.findall('[^0-9]', rad)) != 0:
            return self.invalid_message(message)
        if len(re.findall('[^0-9]', info_bound)) != 0:
            return self.invalid_message(message)
        if (int(rad) > 50 or int(info_bound) > 20 or int(info_bound) <= 0 or int(rad) <=0):
             return self.invalid_message(message)
        
        lat_long = ""
        msg_time = ""
        if (client in self.recent_message):
            lat_long = self.recent_message[client][4]
            msg_time = self.recent_message[client][5]
        else:
            print("client not in recent messages")
            return self.invalid_message(message)
             
        
        delta_t = time.time() - float(msg_time)
        if (delta_t >= 0):
            delta_t = f"+{delta_t}"
        else:
            delta_t = f"-{delta_t}"

        google_api_result = await self.use_api(lat_long, rad, info_bound)
        #google_api = str(google_api_result)
        new_message = f"AT {self.server_name} {delta_t} {client} {lat_long} {msg_time}\n{google_api_result}\n\n"
        #new_message = f"AT {self.server_name} {delta_t} {client} {lat_long} {msg_time}"
       
        return new_message

    # change inputted latitude and longitude to correct format for api call
    def separate_lat_long(self, location):
        # determine second +/-
        i = location.find('+', 1, len(location) - 1)
        if i == -1:
            # second is - 
            i = location.find('-', 1, len(location) -1)
        lat = location[0:i]
        lat = ''.join(re.findall('[0-9.-]', lat))
        lon = location[i:]
        lon = ''.join(re.findall('[0-9.-]', lon))
        return lat, lon
    
    # make api call to google places
    async def use_api(self, lat_long, rad, max_info):
        # get rid of all +'s and 
        lat, lon = self.separate_lat_long(lat_long)
        location = lat + ',' + lon
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        logger.info(f"Sending request to Google Places")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params={"location": location, "radius": rad, "key": API_KEY}) as response:
                logger.info(f"Status: {response.status}")
                html = await response.text()
                data = json.loads(html)
        results = data['results']
        logger.info(f"Retrieved results from google places")
        # ensure that only max_results are returned
        data["results"] = results[0:int(max_info)]
        ret = json.dumps(data)
        return ret
     

    
    def at(self, message):
        # send a message recieved to your neighbors via a flooding algorithm
        message = message.split()
        should_flood = True
        if (len(message) != 6):
            self.invalid_message(message)
            logger.info("Bad AT message, will not flood")
            return False
        at, orig_server, delta_t, client, lat_long, msg_time = message
        if (message in self.recent_message.values()):
            old_msg = self.recent_message[client]
            old_msg_time = old_msg[5]
            if (float(msg_time) > float(old_msg_time)):
                # message needs to be updated!
                #print("Updating Flooded Client Data")
                logger.info("Updating Flooded Client Data")
                self.recent_messages[client] = message
            else:
                #print("Flooded Message has Already been Recieved by Server")
                logger.info("Flooded Message has Already been Recieved by Server")
                should_flood = False
        else:
            # server has no info about this client
            #print("server has no info about this client")
            self.recent_message[client] = message
            logger.info("Imputting Flooded Client Data")
        
        return should_flood
            

    
    # error message for invalid message
    def invalid_message(self, message):
        logger.info("Bad Message")
        return f"? {message}"
    
          

    async def flooding(self, message):
        # send message to each neighbor, and they will send it to theirs until everyone has it
        for neighbor in self.neighbor_list:
            try:
                reader, writer = reader, writer = await asyncio.open_connection('127.0.0.1', neighbor)
            except:
                logger.info(f"Couldn't connect to the following server: {neighbor}")
                continue
            logger.info(f"Flooding the following message from {self.server_name} to {neighbor}: {message}")
            writer.write(message.encode())
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            logger.info(f"Message Successfully Sent")
		
		
def my_port(name):
	port = 8888
	if name == "port1":
		port = 20384
	if name == "port2":
		port = 20385
	if name == "port3":
		port = 20386
	if name == "port4":
		port = 20387
	if name == "port5":
		port = 20388
	return port
	

def neighbor_list(name):
	neighbors = list()
	if name == "port1":
		neighbors.append(20386)
		neighbors.append(20385)
	if name == "port2":
		neighbors.append(20387)
		neighbors.append(20386)
		neighbors.append(20384)
	if name == "port3":
		neighbors.append(20388)
		neighbors.append(20384)
		neighbors.append(20385)
	if name == "port4":
		neighbors.append(20385)
		neighbors.append(20388)
	if name == "port5":
		neighbors.append(20387)
		neighbors.append(20386)
	return neighbors





def main():
    parser = argparse.ArgumentParser(
                    prog='server.py',
                    description='Create and Run Server')
    parser.add_argument('server')
    args = parser.parse_args()
    #print(args.filename, args.count, args.verbose)


    logger.info("Server Started: {}".format(args.server))
    # instantiate server
    server = Server(args.server)

    asyncio.run(server.main())




if __name__ == '__main__':
    main()
