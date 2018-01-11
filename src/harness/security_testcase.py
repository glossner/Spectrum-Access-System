#    Copyright 2016 SAS Project Authors. All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
"""Specialized implementation of SasTestCase for all SCS/SDS/SSS testcases."""

import json
import logging
import os
import re
import socket
import urlparse

from OpenSSL import SSL, crypto


import sas
import sas_testcase
import json

class CiphersOverload(object):
  """Overloads the ciphers and client certificate used by the SAS client.
  Upon destruction, restores the original ciphers and certificate.
   """

  def __init__(self, sas, ciphers, client_cert, client_key):
    self.sas = sas
    self.ciphers = ciphers
    self.client_cert = client_cert
    self.client_key = client_key
    self.original_ciphers = None
    self.original_client_cert = None
    self.original_client_key = None

  def __enter__(self):
    self.original_ciphers = self.sas._tls_config.ciphers
    self.original_client_cert = self.sas._tls_config.client_cert
    self.original_client_key = self.sas._tls_config.client_key
    self.sas._tls_config.ciphers = self.ciphers
    self.sas._tls_config.client_cert = self.client_cert
    self.sas._tls_config.client_key = self.client_key

  def __exit__(self, type, value, traceback):
    self.sas._tls_config.ciphers = self.original_ciphers
    self.sas._tls_config.client_cert = self.original_client_cert
    self.sas._tls_config.client_key = self.original_client_key


class SecurityTestCase(sas_testcase.SasTestCase):

  def setUp(self):
    self._sas, self._sas_admin = sas.GetTestingSas()
    # Note that we disable the admin.Reset(), to avoid 'unexpected' request
    # to SAS UUT before a test really starts.
    # Tests changing the SAS UUT state must explicitly call the SasReset()

  def SasReset(self):
    """Resets the SAS UUT to its initial state."""
    self._sas_admin.Reset()

  def assertTlsHandshakeSucceed(self, base_url, ciphers, client_cert, client_key,IsVerifyServercert=False):
    """Checks that the TLS handshake succeed with the given parameters.

    Attempts to establish a TLS session with the given |base_url|, using the
    given |ciphers| list and the given certificate key pair.
    Checks that he SAS UUT response must satisfy all of the following conditions:
    - The SAS UUT agrees to use a cipher specified in the |ciphers| list
    - The SAS UUT agrees to use TLS Protocol Version 1.2
    - Valid Finished message is returned by the SAS UUT immediately following
      the ChangeCipherSpec message
    """
    url = urlparse.urlparse('https://' + base_url)
    client = socket.socket()
    client.connect((url.hostname, url.port or 443))
    logging.debug("OPENSSL version: %s" % SSL.SSLeay_version(SSL.SSLEAY_VERSION))
    logging.debug('TLS handshake: connecting to: %s:%d', url.hostname,
                  url.port or 443)
    logging.debug('TLS handshake: ciphers=%s', ':'.join(ciphers))
    logging.debug('TLS handshake: privatekey_file=%s', client_key)
    logging.debug('TLS handshake: certificate_file=%s', client_cert)
    logging.debug('TLS handshake: certificate_chain_file=%s',
                  self._sas._tls_config.ca_cert)

    ctx = SSL.Context(SSL.TLSv1_2_METHOD)
    ctx.set_cipher_list(':'.join(ciphers))
    ctx.use_certificate_file(client_cert)
    ctx.use_privatekey_file(client_key)
    ctx.load_verify_locations(self._sas._tls_config.ca_cert)

    client_ssl_informations = []
    def _InfoCb(conn, where, ok):
      client_ssl_informations.append(conn.get_state_string())
      logging.debug('TLS handshake info: %d|%d %s', where, ok, conn.get_state_string())
      return ok
    ctx.set_info_callback(_InfoCb)

    if IsVerifyServercert:
      default_values = json.load(
                      open(os.path.join('testcases', 'configs', 'test_WINNF_FT_S_SCS_20', 'default.config')))


    def _ValidateSeverCertificateCb(conn, cert, errnum, depth, ok):
        certsubject = crypto.X509Name(cert.get_subject())
        commonname = certsubject.commonName
        logging.debug('TLS handshake verify: certificate: %s  -> %d', commonname, ok)
        if(default_values["Subject"] == crypto.X509Name(cert.get_subject()).commonName ):
          cnotBefore = cert.get_notBefore()
          cnotAfter = cert.get_notAfter()
          pubkey = cert.get_pubkey()
          serial_number = cert.get_serial_number()
          certsubject = crypto.X509Name(cert.get_issuer())
          commonname = certsubject.commonName
          # only for potential debugging info...
          logging.debug('serial number %s ', cert.get_serial_number())
          logging.debug('signature algorithm %s ', cert.get_signature_algorithm())
          logging.debug('Number of bits in Publick key  %s ', pubkey.bits())
          # Checking the validity of the date of the certificate is taken care by the pyopenssl v17.5.0 library
          self.assertIsNotNone(cnotAfter)
          logging.debug('Not After %s ', cnotAfter)
          self.assertIsNotNone(cnotBefore)
          logging.debug('Not Before %s ', cnotBefore)
          logging.debug('Common Name ->subject %s ', crypto.X509Name(cert.get_subject()).commonName)
          logging.debug('Common Name ->Issuer %s ', crypto.X509Name(cert.get_issuer()).commonName)
          logging.debug('organizationName %s ', crypto.X509Name(cert.get_issuer()).organizationName )
          logging.debug('ROLE  %s ', cert.get_extension(4))
          logging.debug('CA  %s ', cert.get_extension(2))
          self.assertEqual(cert.get_issuer().commonName, default_values["Issuer"])
          self.assertEqual(cert.get_subject().commonName, default_values["Subject"])
          self.assertEqual(cert.get_subject().countryName , default_values["countryName"])
          self.assertEqual(cert.get_subject().stateOrProvinceName  , default_values["stateOrProvinceName"])
          self.assertEqual(cert.get_subject().localityName   , default_values["localityName"])
          self.assertEqual(cert.get_subject().organizationName   , default_values["organizationName"])
          self.assertEqual(cert.get_subject().organizationalUnitName    , default_values["organizationalUnitName"])
          self.assertEqual(cert.get_subject().commonName   , default_values["commonName"])
          self.assertGreaterEqual(serial_number, 0,serial_number)
          self.assertLess(len(str(serial_number)), 21)
          self.assertEqual(cert.get_version(), 2)
          self.assertGreaterEqual(pubkey.bits(), 2048)

          policy_sas = str(cert.get_extension(5))
          #The SAS UUT provided certificate does not contain the following custom SAS OIDs:
          self.assertIn("1.3.6.1.4.1.46609.1.1",policy_sas)
          self.assertNotIn("1.3.6.1.4.1.46609.1.2",policy_sas)
          self.assertNotIn("1.3.6.1.4.1.46609.1.3",policy_sas)
          self.assertNotIn("1.3.6.1.4.1.46609.1.4",policy_sas)
          self.assertNotIn("1.3.6.1.4.1.46609.1.5",policy_sas)
          self.assertNotIn("1.3.6.1.4.1.46609.1.7",policy_sas)
          self.assertIn("1.3.6.1.4.1.46609.1.6",policy_sas, 0)
          policy_ca = str(cert.get_extension(2))
          self.assertIn("CA:FALSE",policy_ca)
          self.assertNotIn("pathlen",policy_ca, 0)
          logging.debug('ROLE SAS  %s ',policy_sas)
          signature_alogo = cert.get_signature_algorithm()
          signature_alog_list = ["sha256WithRSAEncryption","sha384WithRSAEncryption","sha512WithRSAEncryption","ecdsa-with-Sha256","ecdsa-with-Sha384","ecdsa-with-Sha512"]
          self.assertIn(signature_alogo,signature_alog_list)
          logging.info("All fields in certificates are validated successfully")
        return ok
    if IsVerifyServercert:
      ctx.set_verify(SSL.VERIFY_PEER, _ValidateSeverCertificateCb)

    client_ssl = SSL.Connection(ctx, client)

    client_ssl.set_connect_state()
    client_ssl.set_tlsext_host_name(url.hostname)

    try:
      client_ssl.do_handshake()
      logging.info('TLS handshake: succeed')
    except SSL.Error as e:

      logging.exception('TLS handshake: failed:\n%s', '\n'.join(client_ssl_informations))
      raise AssertionError('TLS handshake: failure: %s' % e.message)

    finally:
      client_ssl.close()

    self.assertEqual(client_ssl.get_cipher_list(), ciphers)
    self.assertEqual(client_ssl.get_protocol_version_name(), 'TLSv1.2')

    # tricky part: exact logged message depends of the version of openssl...
    cipher_check_regex = re.compile(r"change.cipher.spec", re.I)
    finished_check_regex = re.compile(r"negotiation finished|finish_client_handshake", re.I)
    def findIndexMatching(array, regex):
      for i, x in enumerate(array):
        if regex.search(x):
          return i
      return -1
    cipher_check_idx = findIndexMatching(client_ssl_informations, cipher_check_regex)
    finished_check_idx = findIndexMatching(client_ssl_informations, finished_check_regex)
    self.assertTrue(cipher_check_idx > 0)
    self.assertTrue(finished_check_idx > 0)
    self.assertTrue(finished_check_idx > cipher_check_idx)

  def doTestCipher(self, cipher, client_cert=None, client_key=None):
    """Does a cipher test as described in SCS/SDS/SSS tests 1 to 5 specification.

    Args:
      cipher: the cipher openSSL string name to test.
      client_cert: optional client certificate file in PEM format to use.
        If 'None' the default CBSD certificate will be used.
      client_key: associated key file in PEM format to use with the optionally
        given |client_cert|. If 'None' the default CBSD key file will be used.
    """
    client_cert = client_cert or self._sas._GetDefaultCbsdSSLCertPath()
    client_key = client_key or self._sas._GetDefaultCbsdSSLKeyPath()

    # Using pyOpenSSL low level API, does the SAS UUT server TLS session checks.
    self.assertTlsHandshakeSucceed(self._sas_admin._base_url, [cipher],
                                   client_cert, client_key)

    # Does a regular CBSD registration
    self.SasReset()
    device_a = json.load(
        open(os.path.join('testcases', 'testdata', 'device_a.json')))
    with CiphersOverload(self._sas, [cipher], client_cert, client_key):
      self.assertRegistered([device_a])

  def assertTlsHandshakeFailure(self, client_cert, client_key, ca_cert=None, ciphers=None, ssl_method=None):
    """
    Does a tls handshake with different client_cert and client_key
    Args:
      client_cert: optional client certificate file in PEM format to use.
      client_key: associated key file in PEM format to use with the client_cert
    """

    url = urlparse.urlparse('https://' + self._sas_admin._base_url)
    client = socket.socket()
    client.connect((url.hostname, url.port or 443))
    logging.debug("OPENSSL version: %s" % SSL.SSLeay_version(SSL.SSLEAY_VERSION))
    logging.debug('TLS handshake: connecting to: %s:%d', url.hostname,
                  url.port or 443)
    logging.debug('TLS handshake: privatekey_file=%s', client_key)
    logging.debug('TLS handshake: certificate_file=%s', client_cert)
    if (ssl_method is not None) :
      ctx = SSL.Context(ssl_method)
    else:
      ctx = SSL.Context(SSL.TLSv1_2_METHOD)
    if ciphers is not None:
       ctx.set_cipher_list(ciphers)
    ctx.use_certificate_file(client_cert)
    ctx.use_privatekey_file(client_key)
    if ca_cert is not None:
      self._sas._tls_config.ca_cert = ca_cert
      ctx.load_verify_locations(self._sas._tls_config.ca_cert)

    client_ssl_informations = []
    def _InfoCb(conn, where, ok):
      client_ssl_informations.append(conn.get_state_string())
      logging.debug('TLS handshake info: %d|%d %s', where, ok, conn.get_state_string())
      return ok
    ctx.set_info_callback(_InfoCb)

    client_ssl = SSL.Connection(ctx, client)
    client_ssl.set_connect_state()
    client_ssl.set_tlsext_host_name(url.hostname)
    
    try:
      client_ssl.do_handshake()
      logging.info('TLS handshake: succeed')
      self.fail(msg="TLS Handshake is success. but Expected:TLS handshake failure")
    except SSL.Error as e:
      logging.debug('Received alert_reason:%s' %" ".join(e.message[0][2]))
      self.assertEquals(client_ssl.get_peer_finished(), None)

    finally:
      client_ssl.close()

