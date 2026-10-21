#!/usr/bin/env python3
"""Optional LIVE dev smoke test: send and receive one synthetic event using Entra.

Not invoked by check-ingest.sh. Requires a deployed namespace, authorized network
and DNS, azure-identity and azure-eventhub. No secrets are printed.
"""
import argparse
import asyncio
import datetime
import json
import socket
import uuid


async def verify(args):
    from azure.eventhub import EventData, TransportType
    from azure.eventhub.aio import EventHubConsumerClient, EventHubProducerClient
    from azure.identity.aio import DefaultAzureCredential

    addresses = sorted({item[4][0] for item in socket.getaddrinfo(args.namespace, 443)})
    # Compare with the deployed private endpoint rather than trusting any private IP.
    if set(addresses) != {args.expected_private_ip}:
        raise RuntimeError("DNS does not resolve exclusively to the expected private endpoint IP.")

    correlation_id = str(uuid.uuid4())
    event = {
        "type": "synthetic-validation",
        "environment": "dev",
        "correlation_id": correlation_id,
        "measured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "hu22-smoke-test",
    }
    matched = asyncio.Event()

    async def on_event(partition_context, message):
        if message is None:
            return
        try:
            received = json.loads(message.body_as_str())
        except (ValueError, UnicodeError):
            return
        if isinstance(received, dict) and received.get("correlation_id") == correlation_id:
            matched.set()

    async def on_error(partition_context, error):
        raise RuntimeError("Event Hubs receive failed; check identity, roles and private connectivity.") from error

    start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=30)
    async with DefaultAzureCredential() as credential:
        common = dict(
            fully_qualified_namespace=args.namespace,
            eventhub_name=args.eventhub,
            credential=credential,
            transport_type=TransportType.AmqpOverWebsocket,
        )
        async with EventHubConsumerClient(consumer_group=args.consumer_group, **common) as consumer:
            async with EventHubProducerClient(**common) as producer:
                batch = await producer.create_batch()
                batch.add(EventData(json.dumps(event)))
                # A time-based starting position also captures a message sent before receive starts.
                await producer.send_batch(batch)
                receive = asyncio.create_task(consumer.receive(
                    on_event=on_event, on_error=on_error, starting_position=start, max_wait_time=5,
                ))
                wait_for_match = asyncio.create_task(matched.wait())
                try:
                    done, _ = await asyncio.wait(
                        [receive, wait_for_match], timeout=args.timeout,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if receive in done:
                        receive.result()
                    if not matched.is_set():
                        raise RuntimeError("The synthetic event was not received within the smoke-test timeout.")
                finally:
                    receive.cancel()
                    wait_for_match.cancel()
                    await asyncio.gather(receive, wait_for_match, return_exceptions=True)
    print(json.dumps({"result": "PASS", "correlation_id": correlation_id,
                      "scope": "dev synthetic send/receive over private DNS, Entra and AMQP-WebSockets"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True, help="Normal namespace FQDN from telemetry_alerts output")
    parser.add_argument("--expected-private-ip", required=True, help="Actual approved private endpoint IP from Azure")
    parser.add_argument("--eventhub", default="alerts")
    parser.add_argument("--consumer-group", default="verification")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--confirm-dev", action="store_true", required=True,
                        help="Confirm this is the development namespace with synthetic data")
    args = parser.parse_args()
    if not args.namespace.endswith(".servicebus.windows.net") or "/" in args.namespace:
        parser.error("Use the namespace FQDN, without a scheme or path.")
    if args.timeout < 1 or args.timeout > 300:
        parser.error("The timeout must be between 1 and 300 seconds.")
    asyncio.run(verify(args))


if __name__ == "__main__":
    main()
