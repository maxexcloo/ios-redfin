/* Host tests of real pd-mapper/QMI replies; only the QRTR transport is replaced. */
#include <stdio.h>
#include <string.h>
#include "pdmapper.h"
#include "qmi.h"

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static uint8_t response[8192];
static uint32_t response_len;

int qrtr_new_server(uint32_t service, uint32_t version, uint32_t instance, uint32_t port)
{
	CHECK(service == PDMAPPER_SERVICE && version == 1 && instance == 1 && port == PDMAPPER_PORT);
	return 0;
}

int qrtr_send(uint32_t type, uint32_t src_port, uint32_t dst_node, uint32_t dst_port,
	      const void *payload, uint32_t len)
{
	CHECK(type == QRTR_TYPE_DATA && src_port == PDMAPPER_PORT && dst_node == 7 && dst_port == 23);
	CHECK(len <= sizeof(response));
	if (len > sizeof(response))
		return -1;
	memcpy(response, payload, len);
	response_len = len;
	return 0;
}

static void domains(const char *service, uint32_t offset, uint8_t count, uint16_t total)
{
	static const char *names[] = { "msm/modem/root_pd", "msm/modem/wlan_pd" };
	struct qrtr_hdr h = { .src_node = 7, .src_port = 23 };
	struct qmi_buf q;
	qmi_start(&q, QMI_REQUEST, 42, 0x21);
	qmi_tlv(&q, 1, service, (uint16_t)strlen(service));
	qmi_tlv_u32(&q, 0x10, offset);
	response_len = 0;
	pdmapper_handle(&h, q.b, (uint32_t)qmi_finish(&q));

	struct qmi_msg m;
	int parsed = qmi_parse(response, response_len, &m);
	CHECK(parsed == 0);
	if (parsed)
		return;
	CHECK(m.type == QMI_RESPONSE && m.txn == 42 && m.id == 0x21);
	uint16_t len;
	const uint8_t *p = qmi_get(&m, 2, &len);
	CHECK(p && len == 4 && !memcmp(p, "\0\0\0\0", 4));
	p = qmi_get(&m, 0x10, &len);
	CHECK(p && len == 2 && !memcmp(p, &total, 2));
	p = qmi_get(&m, 0x12, &len);
	CHECK(p && len >= 1 && p[0] == count);
	if (!p || !len)
		return;
	size_t at = 1;
	for (unsigned i = 0; i < count; i++) {
		size_t n = strlen(names[offset + i]);
		CHECK(at + 1 + n + 9 <= len);
		if (at + 1 + n + 9 > len)
			return;
		CHECK(p[at++] == n);
		CHECK(!memcmp(p + at, names[offset + i], n));
		at += n;
		uint32_t instance, data;
		memcpy(&instance, p + at, 4);
		CHECK(instance == 180 && p[at + 4] == 0);
		memcpy(&data, p + at + 5, 4);
		CHECK(data == 0);
		at += 9;
	}
	CHECK(at == len);
}

int main(void)
{
	CHECK(pdmapper_init() == 0);
	domains("tms/servreg", 0, 2, 2);
	domains("tms/servreg", 1, 1, 2);
	domains("tms/servreg", 3, 0, 2);
	domains("unknown/service", 0, 0, 0);
	if (failures)
		return 1;
	puts("pd-mapper domain-list tests passed");
	return 0;
}
