# API reference

## Base

```{eval-rst}
.. autoclass:: pabo.Construct
   :members: parse, build, size, sizeof, describe, dump
```

## Specifications

```{eval-rst}
.. automodule:: pabo.specify
   :members: Specification, Embedded

.. automodule:: pabo.declarative
   :members: Struct, StructConstruct
```

## Context and expressions

```{eval-rst}
.. automodule:: pabo.context
   :members: Container, Context

.. automodule:: pabo.expressions
   :members: Expr, This, lenof, evaluate
```

## Numbers

```{eval-rst}
.. automodule:: pabo.numeric
   :members: Int, Float, VarInt, ZigZag, Array

.. automodule:: pabo.aliases
```

## Bytes, strings and bits

```{eval-rst}
.. automodule:: pabo.bytes
   :members:

.. automodule:: pabo.strings
   :members: CString, PascalString, PaddedString, GreedyString, Line

.. automodule:: pabo.bits
   :members:

.. automodule:: pabo.packing
   :members: packbits, unpackbits
```

## Wrappers and control flow

```{eval-rst}
.. automodule:: pabo.wrappers
   :members:

.. automodule:: pabo.control
   :members:
```

## Stream positioning

```{eval-rst}
.. automodule:: pabo.stream
   :members: Seek, Tell, Pointer, Peek, Aligned, AlignedSpec, Lazy, LazyValue
```

## Transforms and adapters

```{eval-rst}
.. automodule:: pabo.transforms
   :members: Transformed, Compressed, Checksummed

.. automodule:: pabo.adapters
   :members:
```

## Debugging

```{eval-rst}
.. automodule:: pabo.debug
   :members:
```

## Type hints

```{eval-rst}
.. automodule:: pabo.hints
   :members: Readable, Writable
```

## Errors

```{eval-rst}
.. automodule:: pabo.errors
   :members:
```
