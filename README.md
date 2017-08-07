# ProxyFinder
A ProxyBroker "find" functionality wrapper written to run it in a separate process. It enables running proxybroker.Broker.find() in the background, so it's possible to do other (possibly synchronous) stuff in the main process without being forced to use asyncio library.

## Prerequisites
Only requirement is ProxyBroker itself. You will need latest version from github, as the version in pip repository is outdated.
```
pip install git+https://github.com/constverum/ProxyBroker.git
```

You might also want to downgrade aiohttp to version 2.0.7 due to deprecation warnings or install [fork with a fix for that instead](https://github.com/Lookyan/ProxyBroker.git) (though you might still get them anyway).

## Usage
1. Create ProxyFinder instance, specifying options as keyword arguments like in proxybroker.Broker.find() (they will be passed over to that function call)
2. Call start() to spawn separate process and start grabbing proxies
3. Do your work while proxy grabbing is taking place in the background
4. To access found proxies, use ProxyFinder.proxies list of proxybroker.Proxy objects (call update_proxies() before doing so, otherwise you will get only the ones since last update_proxies() call)
5. After you finish doing your work, call stop() to exit gracefully

## Example
```python
from proxyfinder import ProxyFinder
import time

def main():
	# find at most 100 HTTP or HTTPS proxies and exit (note that if limit is not specified or 0, proxy grabbing will last until stop() is called)
	finder = ProxyFinder(types=['HTTP', 'HTTPS'], limit=100) 
	finder.start()

	time.sleep(10) 			# do your stuff here, simulating some work using time.sleep()

	finder.update_proxies()
	print(finder.proxies) 	# use found proxies in desired way
	finder.stop()
	
if __name__ == '__main__':
	main()
```

## Acknowledgments
* [Constverum](https://github.com/constverum) for creating the best python proxy finder and checker library [ProxyBroker](https://github.com/constverum/ProxyBroker)

## Notes
This section is for summing up some of the author's research on trying to run ProxyBroker successfully, and why using another process and not a thread has been chosen. This is intended to provide some information to people which might run into the same issues as author's.

### ProxyBroker 'serve' functionality flaws
ProxyBroker serve functionality isn't as well coded as one would expect it to be. Mainly, server distributes requests only to the topmost proxies (from the pool list), which often results in the same proxies being used constantly. There's no way to specify through CLI arguments if that's a desired behaviour. One might want to do "rotation" of proxy pool, so that load is spread evenly on each proxy. And this is in fact what some people tried to do in their forks of ProxyBroker, but they don't seem to work on python 3.6 with latest asyncio and aiohttp (last commit to ProxyBroker was in June 2016, and it seems it's not supported by the author anymore). Moreover, proxy server will just hang after <1 hour of running. And last, but not least, trying to change anything in the code of ProxyBroker might just break it in ways that you wouldn't expect it to. It will just hang without a proper debugging information. Summing all that up, let's shift our attitude from "trying to fix it" to "don't change anything, just run find() in another thread".

### Separate thread approach
ProxyBroker doesn't like threads. If you try to run proxybroker.Broker.find() in a separate thread like this:

```python
async def print_proxy(proxies):
	while True:
		proxy = await proxies.get()
		if proxy is None:
			break
		else:
			print(proxy)

def run_in_thread():
	loop = asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	proxies = asyncio.Queue()
	broker = proxybroker.Broker(proxies)
	tasks = asyncio.gather(broker.find(types=['HTTP'], limit=10), print_proxy(proxies))
	loop.run_until_complete(tasks)

asyncio_thread = threading.Thread(target=run_in_thread)
asyncio_thread.start()
asyncio_thread.join()
```

It will just hang. This is due to a select.select() call in asyncio library waiting without a timeout for a descriptor to be ready for reading, but it never becomes ready. I can only guess it's a bug in ProxyBroker, because any other asyncio code will run just fine in another thread after setting a new event loop for that thread:

```python
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
```

As we have already shifted our attitude from trying to fix ProxyBroker asyncio code, discovering that running it in a separate thread doesn't work, we come up with a solution to just use other process. And it works probably because ProxyBroker can't tell the difference between main process' "MainThread" and child process' "MainThread". It's a resource-wasteful approach, but it's reasonable considering the amount of time spent on writing it vs. the amount of time one would spend trying to fix ProxyBroker.