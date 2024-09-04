import asyncio
import argparse
import logging

def my_port(name):
	port = 8888
	if name == "server1":
		port = 20384
	if name == "server2":
		port = 20385
	if name == "server3":
		port = 20386
	if name == "server4":
		port = 20387
	if name == "server5":
		port = 20388
	return port

class Client:
    def __init__(self, my_server, name='client'):
        self.port = my_port(my_server)
        self.name = name

    # based off of https://docs.python.org/3/library/asyncio-stream.html#examples
    async def tcp_echo_client(self, message):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        print(f'{self.name} send: {message!r}')
        writer.write(message.encode())
        await writer.drain()

        data = await reader.read(10000000)
        print(f'{self.name} received: {data.decode()!r}')

        print('Close the connection')
        writer.close()
        await writer.wait_closed()

    def main(self):
        while True:
            message = input("Please input the next message to send: ")
            asyncio.run(self.tcp_echo_client(message))



if __name__ == '__main__':

    parser = argparse.ArgumentParser(
                    prog='client.py',
                    description='Create and Run Client')
    parser.add_argument('my_server')
    args = parser.parse_args()
    #print(args.filename, args.count, args.verbose)


    logging.info("Client Started, connected to server: {}".format(args.my_server))
    # instantiate client
    client = Client(args.my_server)  # using the default settings
    asyncio.run(client.main())