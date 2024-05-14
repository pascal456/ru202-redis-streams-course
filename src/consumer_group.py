"""Example of consumer groups.

A producer, which pushes increasing natural numbers into a stream at semi-random
intervals.

A consumer group containing three consumers, each of which reads messages from the
stream and calculates whether or not the number in the message is prime.

A chaos process which periodically randomly terminates one of the consumers and
restarts it, forcing it to recover and resume its former workload as it restarts.

Before each run, the code will reset the stream.

From the output, we can see three consumers (BOB-0, BOB-1, BOB-2)
working together as a consumer group to process a stream of numbers and
determine if each number is prime or not.
Each consumer processes messages one-by-one, but as the message processing
takes a variable amount of time (`sleep(random.random())`), it's not possible
to determine which consumer will process which message.

Periodically, a chaos function (CHAOS) restarts one of the consumers,
which then has to read its pending entry list so that it can resume
processing where it left off.
The program also starts a producer process, which doesn't output
anything but will keep pushing increasing natural numbers to the
stream at semi-random intervals.
"""
import random
from threading import Thread
from multiprocessing import Process
from time import sleep
from util.connection import get_connection

KEY = "numbers"
GROUP = "primes"
MEMBERS = 3


def prime(a):
    """Test with an simple primality test.

    Credit: https://rosettacode.org/wiki/Primality_by_trial_division#Python
    """
    sleep(random.random())
    return not (a < 2 or any(a % x == 0 for x in range(2, int(a**0.5) + 1)))


def setup():
    """Initialize the Stream and the primes consumers group."""
    redis = get_connection()
    redis.delete(KEY)
    redis.xgroup_create(KEY, GROUP, mkstream=True)


def producer_func():
    """Natural Numbers Stream producer."""
    redis = get_connection("PRODUCER")
    n = 0

    while True:
        data = {"n": n}
        _id = redis.xadd(KEY, data)
        n += 1
        sleep(random.random() / MEMBERS)


def consumer_func(name):
    """Implement a group consumer."""
    redis = get_connection(name)
    timeout = 100
    retries = 0
    recovery = True
    from_id = "0"

    while True:
        count = random.randint(1, 5)
        reply = redis.xreadgroup(
            GROUP, name, {KEY: from_id}, count=count, block=timeout
        )
        if not reply:
            if retries == 5:
                print(f"{name}: Waited long enough - bye bye...")
                break
            retries += 1
            timeout *= 2
            continue

        timeout = 100
        retries = 0

        if recovery:
            # Verify that there are messages to recover. The zeroth member of the
            # reply contains the following:
            #
            # At element 0: the name of the stream
            #
            # At element 1: a list of pending messages, if any.
            #
            # If there are messages, we recover them.
            #
            # Example contents for "reply":
            #
            # [['numbers', [('1557775037438-0', {'n': '8'})]]]
            if reply[0][1]:
                print(f"{name}: Recovering pending messages...")
            else:
                # If there are no messages to recover, switch to fetching new messages
                # and call xreadgroup again.
                recovery = False
                from_id = ">"
                continue

        # Process the messages
        for _, messages in reply:
            for message in messages:
                n = int(message[1]["n"])
                if prime(n):
                    print(f"{name}: {n} is a prime number")
                redis.xack(KEY, GROUP, message[0])


def new_consumer(name):
    """Start a new consumer subrocess."""
    consumer = Process(target=consumer_func, args=(name,))
    consumer.start()
    return (name, consumer)


def chaos_func(consumers):
    """Kill (and revives) consumers at random."""
    while True:
        # Roll a pair of dice to determine the verdict
        if random.randint(2, 12) == 2:
            # And another dice to find the victim
            idx = random.randrange(0, stop=len(consumers))
            name = consumers[idx][0]
            consumer = consumers[idx][1]
            consumer.terminate()
            consumers[idx] = new_consumer(name)
            print(f"CHAOS: Restarted {name}")
        sleep(random.random())


if __name__ == "__main__":
    setup()

    consumers = []
    for i in range(MEMBERS):
        consumers.append(new_consumer(f"BOB-{i}"))

    Thread(target=chaos_func, args=(consumers,)).start()
    producer_func()
