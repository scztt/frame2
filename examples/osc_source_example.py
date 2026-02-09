"""
Example demonstrating OSCSource usage.

OSCSource listens for OSC (Open Sound Control) messages on a UDP port
and notifies subscribers when messages arrive.

Run this example, then send OSC messages using TouchOSC, Max/MSP, or Python:

    from pythonosc.udp_client import SimpleUDPClient
    client = SimpleUDPClient("127.0.0.1", 8000)
    client.send_message("/volume", [0.75])
    client.send_message("/position", [100, 200, 300])
"""

from frame.action_observable import Model, PropertyAction, ReplaceAction, OSCSource, OSCSourceSettings, PropertyObserver, LogObserver
import time


def example_single_value():
    """Example: OSC source extracting single value at index."""
    print("\n=== Example 1: Single Value Extraction ===")
    print("Listening on port 8000 for /volume messages")
    print("Send OSC: /volume [0.75]")
    print("Press Ctrl+C to stop\n")

    # Create model
    model = Model({"volume": 0.0})

    # Create OSC source that extracts first value
    osc = OSCSource(OSCSourceSettings(port=8000, address="/volume", value_index=0))  # Extract first value

    # Connect: OSC -> PropertyAction -> Model
    osc.subscribe(lambda value: model.emit(PropertyAction("volume", ReplaceAction(value))))

    # Watch model changes
    prop_obs = PropertyObserver("volume")
    log_obs = LogObserver(prefix="Volume")
    prop_obs >> log_obs
    model.subscribe(prop_obs)

    # Start listening
    osc.run()

    try:
        # Keep running until interrupted
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        osc.stop()


def example_multiple_values():
    """Example: OSC source receiving multiple values as array."""
    print("\n=== Example 2: Multiple Values (Array) ===")
    print("Listening on port 8001 for /position messages")
    print("Send OSC: /position [100, 200, 300]")
    print("Press Ctrl+C to stop\n")

    # Create model
    model = Model({"position": [0, 0, 0]})

    # Create OSC source that returns all values
    osc = OSCSource(OSCSourceSettings(port=8001, address="/position", value_index=None))  # Return all values as list

    # Connect: OSC -> PropertyAction -> Model
    osc.subscribe(lambda values: model.emit(PropertyAction("position", ReplaceAction(values))))

    # Watch model changes
    prop_obs = PropertyObserver("position")
    log_obs = LogObserver(prefix="Position")
    prop_obs >> log_obs
    model.subscribe(prop_obs)

    # Start listening
    osc.run()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        osc.stop()


def example_multiple_sources():
    """Example: Multiple OSC sources feeding into same model."""
    print("\n=== Example 3: Multiple OSC Sources ===")
    print("Listening on:")
    print("  - port 8002 for /control/volume")
    print("  - port 8003 for /control/pan")
    print("Press Ctrl+C to stop\n")

    # Create model with multiple fields
    model = Model({"volume": 0.5, "pan": 0.0})

    # Volume control
    volume_osc = OSCSource(OSCSourceSettings(port=8002, address="/control/volume", value_index=0))
    volume_osc.subscribe(lambda value: model.emit(PropertyAction("volume", ReplaceAction(value))))

    # Pan control
    pan_osc = OSCSource(OSCSourceSettings(port=8003, address="/control/pan", value_index=0))
    pan_osc.subscribe(lambda value: model.emit(PropertyAction("pan", ReplaceAction(value))))

    # Watch both fields
    volume_obs = PropertyObserver("volume")
    pan_obs = PropertyObserver("pan")

    volume_log = LogObserver(prefix="Volume")
    pan_log = LogObserver(prefix="Pan")

    volume_obs >> volume_log
    pan_obs >> pan_log

    model.subscribe(volume_obs)
    model.subscribe(pan_obs)

    # Start both sources
    volume_osc.run()
    pan_osc.run()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        volume_osc.stop()
        pan_osc.stop()


def send_test_messages():
    """Helper: Send test OSC messages to the examples."""
    from pythonosc.udp_client import SimpleUDPClient
    import time

    print("\n=== Sending Test Messages ===\n")

    # Example 1: Volume
    client1 = SimpleUDPClient("127.0.0.1", 8000)
    print("Sending to /volume...")
    for i in range(5):
        value = i * 0.2
        client1.send_message("/volume", [value])
        print(f"  Sent: {value}")
        time.sleep(0.5)

    time.sleep(1)

    # Example 2: Position
    client2 = SimpleUDPClient("127.0.0.1", 8001)
    print("\nSending to /position...")
    for i in range(3):
        values = [i * 10, i * 20, i * 30]
        client2.send_message("/position", values)
        print(f"  Sent: {values}")
        time.sleep(0.5)

    time.sleep(1)

    # Example 3: Multiple
    client3 = SimpleUDPClient("127.0.0.1", 8002)
    client4 = SimpleUDPClient("127.0.0.1", 8003)
    print("\nSending to /control/volume and /control/pan...")
    for i in range(4):
        vol = 0.25 * i
        pan = -1.0 + (0.5 * i)
        client3.send_message("/control/volume", [vol])
        client4.send_message("/control/pan", [pan])
        print(f"  Sent: volume={vol}, pan={pan}")
        time.sleep(0.5)

    print("\nDone sending test messages!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "send":
            send_test_messages()
        elif sys.argv[1] == "1":
            example_single_value()
        elif sys.argv[1] == "2":
            example_multiple_values()
        elif sys.argv[1] == "3":
            example_multiple_sources()
        else:
            print("Usage:")
            print("  python osc_source_example.py 1     # Run example 1")
            print("  python osc_source_example.py 2     # Run example 2")
            print("  python osc_source_example.py 3     # Run example 3")
            print("  python osc_source_example.py send  # Send test messages")
    else:
        print("OSC Source Examples\n")
        print("Choose an example:")
        print("  1 - Single value extraction (port 8000, /volume)")
        print("  2 - Multiple values array (port 8001, /position)")
        print("  3 - Multiple sources (ports 8002-8003)")
        print("\nUsage:")
        print("  python osc_source_example.py 1")
        print("\nTo send test messages (in another terminal):")
        print("  python osc_source_example.py send")
