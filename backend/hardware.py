"""Read-only EtherNet/IP ListIdentity. There are no programming/output services."""
import asyncio
import ipaddress
import struct


def parse_identity(payload: bytes) -> dict:
    if len(payload) < 2:
        raise ValueError('Invalid EtherNet/IP identity response.')
    count, = struct.unpack_from('<H', payload)
    offset = 2
    for _ in range(count):
        if offset + 4 > len(payload):
            break
        kind, length = struct.unpack_from('<HH', payload, offset)
        offset += 4
        item = payload[offset:offset+length]
        offset += length
        if kind != 0x0C:
            continue
        if len(item) < 33:
            raise ValueError('Truncated device identity.')
        vendor, device_type, product = struct.unpack_from('<HHH', item, 18)
        name_length = item[32]
        if len(item) < 33 + name_length:
            raise ValueError('Truncated product name.')
        name = item[33:33+name_length].decode('ascii', errors='replace')
        return {'vendor_id': vendor, 'device_type': device_type, 'product_code': product,
                'revision': f'{item[24]}.{item[25]}', 'product_name': name,
                'target_family_matches': vendor == 1 and '1400' in name and 'micro' in name.lower()}
    raise ValueError('No CIP identity item returned by this device.')


async def check_identity(address: str) -> dict:
    ip = ipaddress.IPv4Address(address)
    if not any(ip in ipaddress.IPv4Network(n) for n in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']):
        raise ValueError('Use the PLC private LAN IPv4 address (10.x, 172.16-31.x or 192.168.x).')
    writer = None
    try:
        async with asyncio.timeout(4):
            reader, writer = await asyncio.open_connection(str(ip), 44818)
            context = b'TRISHUL1'
            writer.write(struct.pack('<HHII8sI', 0x63, 0, 0, 0, context, 0))
            await writer.drain()
            header = await reader.readexactly(24)
            command, length, session, status, returned_context, options = struct.unpack('<HHII8sI', header)
            if command != 0x63 or status != 0 or returned_context != context or not 2 <= length <= 4096:
                raise ValueError('Unexpected EtherNet/IP identity response.')
            identity = parse_identity(await reader.readexactly(length))
            return {'connected': True, 'ip': str(ip), **identity, 'hardware_armed': False,
                    'programming_enabled': False, 'test_enabled': False,
                    'message': 'Identity verified only. Programming blocked until the existing ladder/register map and electrical interface are reviewed.'}
    except (OSError, TimeoutError, asyncio.IncompleteReadError):
        raise ValueError('No valid PLC response on EtherNet/IP TCP 44818. Check PLC IP, cable, PC subnet and controller power.')
    finally:
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
