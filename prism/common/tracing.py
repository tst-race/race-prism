#  Copyright (c) 2019-2023 SRI International.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
from contextlib import contextmanager
from logging import INFO, Handler, Logger, LogRecord
from jaeger_client import Config, SpanContext
from jaeger_client.reporter import NullReporter
from opentracing import Tracer, Format, child_of, follows_from, Scope
from typing import Optional, List, Union, Generator

from prism.common.message import PrismMessage, DebugMap

_tracer: Optional[Tracer] = None


class PrismScope:
    def __init__(self, scope: Scope, logger, tags):
        self.scope = scope
        self._logger = logger
        self.tags = tags

    @property
    def context(self) -> SpanContext:
        return self.scope.span.context

    @property
    def trace_id(self) -> str:
        return hex(self.context.trace_id)[2:]

    def msg_tags(self, **kwargs):
        return {**self.tags, **kwargs}

    def tag(self, **kwargs):
        for k, v in kwargs.items():
            self.scope.span.set_tag(k, v)

    def debug(self, msg, **kwargs):
        self.scope.span.log_kv({"event": msg, **kwargs})
        self._logger.debug(msg, **self.msg_tags(**kwargs), trace_id=self.trace_id)

    def error(self, msg, **kwargs):
        self.scope.span.log_kv({"event": msg, **kwargs})
        self._logger.error(msg, **self.msg_tags(**kwargs), trace_id=self.trace_id)

    def warning(self, msg, **kwargs):
        self.scope.span.log_kv({"event": msg, **kwargs})
        self._logger.warning(msg, **self.msg_tags(**kwargs), trace_id=self.trace_id)

    def info(self, msg, **kwargs):
        self.scope.span.log_kv({"event": msg, **kwargs})
        self._logger.info(msg, **self.msg_tags(**kwargs), trace_id=self.trace_id)


def init_tracer(logger: Logger, configuration, service):
    global _tracer
    if _tracer is not None:
        logger.info('Tracer is already initialized - skipping')
        return

    service_name = f'prism:{service}'
    config = Config(
        config={
            'sampler': {'type': 'const', 'param': 1},
            'local_agent': {
                'reporting_host': configuration.get('jaeger_agent_host'),
                'reporting_port': configuration.get('jaeger_agent_port'),
            },
            'logging': configuration.debug,  # log spans as they are produced
        },
        service_name=service_name,
        validate=True,
    )
    _tracer = config.initialize_tracer()  # this call also sets opentracing.tracer;
    if _tracer is None:
        # only the first call above is successful, so we need to create another tracer or use the global instance
        # if someone (e.g., RiB) has already configured the global opentracing.tracer instance
        logger.debug(f'Global tracer already configured - create new one')
        _tracer = config.new_tracer()
    assert _tracer
    if configuration.production:
        _tracer.reporter = NullReporter()  # don't emit anything if in PRODUCTION mode
        logger.debug('Turning off distributed tracing in PRODUCTION mode')
    else:
        logger.info(f'Configured Jaeger service "{service_name}" with agent at ' +
                    f'{configuration.get("jaeger_agent_host")}:{configuration.get("jaeger_agent_port")}')
        # hook into logger to automatically add log events to traced spans:
        trace_handler = TraceHandler()
        trace_handler.setLevel(INFO)
        logger.addHandler(trace_handler)

    logger.debug(f'Tracer {_tracer} with name={service_name} successfully configured')


def tracer() -> Optional[Tracer]:
    global _tracer
    return _tracer


class TraceHandler(Handler):

    def emit(self, record: LogRecord) -> None:
        if tracer():
            scope = tracer().scope_manager.active
            if scope:
                scope.span.log_kv({
                    'level': record.levelname,
                    'message': record.msg,
                    'logger': record.name,
                    'thread': record.threadName,
                })


def create_trace_debug_map(span_ctx: SpanContext) -> Optional[DebugMap]:
    if not span_ctx:
        return None
    # TODO: unify with below
    carrier = {}
    tracer().inject(span_context=span_ctx,
                    format=Format.TEXT_MAP,
                    carrier=carrier)
    return DebugMap(DebugMap.create_trace_info(carrier=carrier))


def inject_span_context(message: PrismMessage, span_ctx: SpanContext) -> PrismMessage:
    if message and span_ctx:
        # create cross-process trace information:
        # unfortunately, Jaeger currently does not support Inject() of BINARY format, so switching to text map
        # see: https://github.com/jaegertracing/jaeger-client-python/issues/224
        # carrier = bytearray()
        # tracer().inject(span_context=span.context,
        #                 format=Format.BINARY,
        #                 carrier=carrier)
        carrier = {}
        tracer().inject(span_context=span_ctx,
                        format=Format.TEXT_MAP,
                        carrier=carrier)
        trace_info = DebugMap.create_trace_info(carrier=carrier)
        # update DebugMap with trace information:
        debug_map = DebugMap(trace_info=trace_info,
                             decryption_key=message.debug_info.decryption_key if message.debug_info else None,
                             next_hop_name=message.debug_info.next_hop_name if message.debug_info else None)
        return message.clone(debug_info=debug_map)
    # idempotent:
    return message


def extract_span_context(message: PrismMessage) -> Optional[SpanContext]:
    if message and message.debug_info:
        # create cross-process trace information:
        carrier = message.debug_info.get_carrier()
        if carrier:
            # NOTE: unfortunately, Jaeger currently does not support Inject() of BINARY format, so switching to
            #   text map
            #   see: https://github.com/jaegertracing/jaeger-client-python/issues/224
            #   otherwise, uncomment the following:
            # return tracer.extract(Format.BINARY, carrier=carrier)
            return tracer().extract(format=Format.TEXT_MAP, carrier=carrier)
    return None


def join_message_context(msg: PrismMessage, operation: str, joining_ctxs: List[SpanContext], **kwargs) -> PrismMessage:
    """Take a message that's part of one trace and join it with a second trace.
    operation = the name of the joining span
    joining_ctxs = the span contexts of the secondary trace(s)
    kwargs = any other information you want to tag the span with"""
    saved_span_ctx = extract_span_context(msg)
    if saved_span_ctx is not None:
        with tracer().start_active_span(operation,
                                        references=[child_of(saved_span_ctx)] +
                                                   [follows_from(ctx) for ctx in joining_ctxs],
                                        tags={'saved_msg_type': f'{msg.msg_type}',
                                              **kwargs}) as joined_scope:
            return inject_span_context(msg, joined_scope.span.context)
    return msg


@contextmanager
def trace_context(
        logger,
        operation: str,
        parent: Optional[Union[PrismMessage, SpanContext]] = None,
        *joining: Union[PrismMessage, SpanContext],
        **tags
) -> Generator[PrismScope, None, None]:
    def context(item: Optional[Union[PrismMessage, SpanContext]]):
        if not item:
            return None
        elif isinstance(item, PrismMessage):
            return extract_span_context(item)
        elif isinstance(item, SpanContext):
            return item
        else:
            raise ValueError("Unexpected context parent.")

    references = []

    if parent:
        references.append(child_of(context(parent)))
    for ref in joining:
        references.append(follows_from(context(ref)))

    with tracer().start_active_span(operation,
                                    references=references,
                                    ignore_active_span=True,
                                    finish_on_close=True,
                                    tags=tags) as scope:
        yield PrismScope(scope, logger, tags=tags)
        scope.close()
