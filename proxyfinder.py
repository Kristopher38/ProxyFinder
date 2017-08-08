import asyncio
import multiprocessing
from proxybroker import Broker
from queue import Empty
from ssl import _create_unverified_context

class ProxyFinder(object):
	"""
		Wrapper for ProxyFinderProcess. Enables running proxybroker.Broker.find() in
		the background, so it's possible to do other (possibly synchronous) stuff in 
		the main process without being forced to use asyncio library.
		Usage:
			1. Call start() to spawn separate process and start grabbing proxies
			2. Do your work while proxy grabbing is taking place in the background
			3. To access found proxies, use ProxyFinder.proxies list of proxybroker.Proxy 
			   objects (call update_proxies() before doing so, otherwise you will get only
			   the ones since last update_proxies() call)
			4. After you finish doing your work, call stop() to exit gracefully
	"""
	
	def __init__(self, types=None, data=None, countries=None,
				post=False, strict=False, dnsbl=None, limit=0):
		"""
			Creates ProxyFinder class instance. All keyword arguments are in the end
			passed down to proxybroker.Broker.find()
			Note: if limit = 0, proxy grabbing will last forever
		"""
		self._results_queue = multiprocessing.Queue()
		self._poison_pill = multiprocessing.Event()
		self._proxy_finder = ProxyFinderProcess(self._results_queue, self._poison_pill, types=types, data=data, 
											countries=countries, post=post, strict=strict, dnsbl=dnsbl, limit=limit)
		self._proxy_finder.daemon = True
		self.proxies = []
		
	def start(self):
		"""
			Spawn separate proxy finder process and start grabbing proxies.
		"""
		self._proxy_finder.start()
		print("ProxyFinder process started")
		
	def stop(self):
		"""
			Gracefully terminate proxy finder process.
		"""
		self._poison_pill.set()
		self._proxy_finder.join()
		print("ProxyFinder process stopped")
		
	def update_proxies(self):
		"""
			Pull proxies which have been put in queue from separated process
			and append them to a ProxyFinder.proxies list.
		"""
		while True:
			try:
				proxy = self._results_queue.get_nowait()
			except Empty:
				break
			else:
				# restore SSLContext, see ProxyFinderProcess.async_to_result
				proxy = self._restore_ssl_context(proxy)
				self.proxies.append(proxy)
				
	def wait_for_proxy(self, timeout=None):
		try:
			proxy = self._results_queue.get(True, timeout)
		except Empty:
			return
		else:
			proxy = self._restore_ssl_context(proxy)
			self.proxies.append(proxy)
			
	def _restore_ssl_context(self, proxy):
		if proxy._ssl_context is None:
			proxy._ssl_context = _create_unverified_context()
			return proxy
				
class ProxyFinderProcess(multiprocessing.Process):
	"""
		Wrapper for proxybroker.Broker.find() which runs it in a separate process 
		so it runs in background.
		Note: if limit = 0, proxy grabbing will last forever
	"""
	
	def __init__(self, proxy_queue, poison_pill, types=None, data=None, countries=None,
				post=False, strict=False, dnsbl=None, limit=0):
		"""
			Creates ProxyFinderProcess class instance. All keyword arguments are in the end
			passed down to proxybroker.Broker.find()
			proxy_queue is a multiprocessing.Queue object which enables access of proxies outside of the process
			poison_pill is a multiprocessing.Event object which enables graceful termination of process if set()
			Note: if limit = 0, proxy grabbing will last forever
		"""
		multiprocessing.Process.__init__(self)
		self.results_queue = proxy_queue # multiprocessing.Queue to access proxies outside of the process
		self.poison_pill = poison_pill	# multiprocessing.Event which terminates process gracefully if set()
		self.types = types or ['HTTP']
		self.data = data or []
		self.countries = countries or []
		self.post = post
		self.strict = strict
		self.dnsbl = dnsbl or []
		self.limit = limit

	async def async_to_results(self):
		"""
			Coroutine that transfers proxybroker.Proxy object from internal asyncio.Queue 
			to multiprocessing.Queue, so it can be accessed outside of the process
		"""
		while not self.poison_pill.is_set():
			proxy = await self.async_queue.get()
			if proxy is None:	# note: if proxy is None, it's a ProxyBroker way of signaling poison pill
				break
			else:
				# because _ssl_context isn't pickable when it's a SSLContext object (it can be a boolean
				# value as well), we have to throw it away (we can reinstate it later by calling 
				# ssl._create_unverified_context(), just like it is done in the ProxyBroker library)
				if proxy._ssl_context != True or proxy._ssl_context != False:	
					proxy._ssl_context = None
				self.results_queue.put(proxy)
		self.broker.stop()	# if we got poison pill, exit gracefully
			
	def run(self):	
		"""
			Starts proxybroker.Broker.find() in a separate process
		"""
		self.async_queue = asyncio.Queue()
		self.broker = Broker(self.async_queue)
		self.tasks = asyncio.gather(self.broker.find(types=self.types, data=self.data, countries=self.countries,
													post=self.post, strict=self.strict, dnsbl=self.dnsbl, limit=self.limit),
									self.async_to_results())
		self.loop = asyncio.get_event_loop()
		self.loop.run_until_complete(self.tasks)