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