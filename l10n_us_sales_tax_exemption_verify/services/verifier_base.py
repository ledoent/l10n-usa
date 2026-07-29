# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Verifier contract.

States differ enormously in what they expose. Texas publishes a queryable
dataset of active permit holders; Florida accepts a batch of registration
numbers and answers a day later; Georgia's GATE programme offers a web form
and nothing else. One interface therefore has to cover three shapes, which is
why ``MODE`` exists and why a manual verifier is a first-class implementation
rather than a fallback.
"""


class VerificationError(Exception):
    """The verification could not be carried out.

    Distinct from a verification that ran and came back negative: an
    unreachable service means we know nothing, whereas "not found" is an
    answer. Callers must not record the former as a failed certificate.
    """


class VerifierBase:
    """Base class for certificate verifiers.

    Subclasses set ``CODE``, ``MODE`` and ``STATES``, and implement
    :meth:`verify`.
    """

    CODE = ""
    NAME = ""
    # api    - answers now, over the wire
    # batch  - accepts a request, answers later out of band
    # manual - a person checked and recorded what they saw
    MODE = "manual"
    # State codes this verifier covers; empty means every state.
    STATES = ()

    def __init__(self, verifier_record):
        self.verifier = verifier_record
        self.env = verifier_record.env
        self.timeout = verifier_record.timeout or 10

    def covers(self, state_code):
        return not self.STATES or state_code in self.STATES

    def verify(self, certificate, state_code, **kwargs):
        """Check ``certificate`` for ``state_code``.

        Returns a dict:
            result   - 'verified' | 'not_found' | 'inconclusive'
            reference- identifier the source matched on, if any
            detail   - short human-readable summary
            payload  - raw response, stored verbatim for the audit trail

        Raises VerificationError when the check could not be performed.
        """
        raise NotImplementedError
