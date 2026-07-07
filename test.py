import time

print(time.strftime("%H:%M:%S", time.localtime()))

# print(time.time())
time1 = time.time()

time.sleep(5)

# print(time.time())
time2 = time.time()


print(time2+10-time1)