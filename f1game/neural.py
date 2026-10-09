# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
import random
from typing import Any, Sequence

Matrix = list[list[float]]


class NeuralNetwork:

    def __init__(self, sizes: Sequence[int], rng: random.Random | None = None,
                 weights: list[Matrix] | None = None, biases: list[list[float]] | None = None) -> None:
        self.sizes = list(sizes)
        rng = rng or random.Random()
        if weights is None or biases is None:
            weights = [[[rng.gauss(0.0, 1.0 / math.sqrt(n_in)) for _ in range(n_in)] for _ in range(n_out)]
                       for n_in, n_out in zip(self.sizes, self.sizes[1:])]
            biases = [[0.0] * n_out for n_out in self.sizes[1:]]
        self.weights: list[Matrix] = weights
        self.biases: list[list[float]] = biases
        self.activations: list[list[float]] = []

    def forward(self, x: Sequence[float]) -> list[float]:
        a = list(x)
        acts = [a]
        tanh = math.tanh
        for W, b in zip(self.weights, self.biases):
            a = [tanh(bj + sum(w * ai for w, ai in zip(row, a))) for row, bj in zip(W, b)]
            acts.append(a)
        self.activations = acts
        return a

    def copy(self) -> "NeuralNetwork":
        return NeuralNetwork(self.sizes, weights=[[row[:] for row in W] for W in self.weights],
                             biases=[b[:] for b in self.biases])

    @property
    def parameter_count(self) -> int:
        return sum(len(W) * len(W[0]) + len(b) for W, b in zip(self.weights, self.biases))

    def mutate(self, rng: random.Random, rate: float, sigma: float) -> None:
        for W, b in zip(self.weights, self.biases):
            for row in W:
                for i in range(len(row)):
                    r = rng.random()
                    if r < 0.02 * rate:
                        row[i] = rng.gauss(0.0, 1.0)
                    elif r < rate:
                        row[i] += rng.gauss(0.0, sigma)
            for j in range(len(b)):
                if rng.random() < rate:
                    b[j] += rng.gauss(0.0, sigma)

    @staticmethod
    def crossover(a: "NeuralNetwork", b: "NeuralNetwork", rng: random.Random) -> "NeuralNetwork":
        weights, biases = [], []
        for Wa, Wb, ba, bb in zip(a.weights, b.weights, a.biases, b.biases):
            W, bias = [], []
            for j in range(len(Wa)):
                src_w, src_b = (Wa, ba) if rng.random() < 0.5 else (Wb, bb)
                W.append(src_w[j][:])
                bias.append(src_b[j])
            weights.append(W)
            biases.append(bias)
        return NeuralNetwork(a.sizes, weights=weights, biases=biases)

    def train_supervised(self, samples: Sequence[tuple[Sequence[float], Sequence[float]]], epochs: int,
                         lr: float, rng: random.Random) -> list[float]:
        order = list(range(len(samples)))
        losses = []
        for _ in range(epochs):
            rng.shuffle(order)
            total = 0.0
            for idx in order:
                x, y = samples[idx]
                out = self.forward(x)
                acts = self.activations
                delta = [(o - t) * (1.0 - o * o) for o, t in zip(out, y)]
                total += sum((o - t) ** 2 for o, t in zip(out, y))
                for layer in range(len(self.weights) - 1, -1, -1):
                    W, b, a_prev = self.weights[layer], self.biases[layer], acts[layer]
                    if layer > 0:
                        prev_delta = [sum(W[j][i] * delta[j] for j in range(len(W))) * (1.0 - a_prev[i] ** 2)
                                      for i in range(len(a_prev))]
                    for j, dj in enumerate(delta):
                        row = W[j]
                        step = lr * dj
                        for i, ai in enumerate(a_prev):
                            row[i] -= step * ai
                        b[j] -= step
                    if layer > 0:
                        delta = prev_delta
            losses.append(total / max(1, len(samples)))
        return losses

    def to_dict(self) -> dict[str, Any]:
        rnd = lambda v: round(v, 5)
        return {"sizes": self.sizes,
                "weights": [[[rnd(w) for w in row] for row in W] for W in self.weights],
                "biases": [[rnd(v) for v in b] for b in self.biases]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NeuralNetwork":
        return cls(data["sizes"], weights=data["weights"], biases=data["biases"])
