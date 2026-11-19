#ifndef IPNET_H
#define IPNET_H
#include <stddef.h>
#include <stdint.h>

int ipnet_init(void);	/* a utun for the WLAN's IPv4; hooks into the radio (link up -> DHCP) */
void ipnet_poll(void);	/* from the link's idle loop */

/* Open a nonblocking utun and write its interface name. The caller owns the fd. */
int ipnet_utun_open(char *name, size_t n);
/* Configure a utun with addresses in network order and the point-to-point default if mask is 0. */
int ipnet_utun_set(const char *name, uint32_t ip, uint32_t gw, uint32_t mask, unsigned mtu);
#endif
