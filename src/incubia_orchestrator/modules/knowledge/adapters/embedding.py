"""Offline embedding seam for tests; production requires an evaluated model."""
import hashlib
import math
import re


class HashEmbedding:
    model_version = "hash-384-v1-offline"
    dimension = 384

    def embed(self, texts):
        result = []
        for text in texts:
            vector = [0.0] * self.dimension
            for token in re.findall(r"\w+", text.casefold()):
                digest = hashlib.sha256(token.encode()).digest()
                slot = int.from_bytes(digest[:4], "big") % self.dimension
                vector[slot] += 1.0 if digest[4] & 1 else -1.0
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0:
                raise ValueError("Cannot embed empty text")
            result.append(tuple(value / norm for value in vector))
        return tuple(result)
