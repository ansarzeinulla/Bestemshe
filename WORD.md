### Part I: The Hook & The Uncharted Domain

**Slide 1: Title & The Hook** *(0:00 - 1:00)*
*(Walk to the center of the stage. Do not look at the screen. Look directly at the professors.)*
"In modern reinforcement learning, we evaluate our models using relative metrics. We use self-play, we use Elo ratings, and we celebrate when a neural network achieves a 99 percent win rate against a baseline. 
`[PAUSE]`
But Elo ratings are an illusion. They hide the absolute mathematical error of the value head. 
Good morning. My name is Ansar Zeinulla from Nazarbayev University. Today, I am going to show you what happens when we benchmark a deep neural network not against another algorithm, but against absolute, ground-truth mathematical reality. To do this, we strongly solved the game of Bestemshe, and mathematically mapped the massive configuration space of Togyzkumalak."

**Slide 2: The Mancala Frontier** *(1:00 - 1:45)*
*(Gesture to the chart)*
"To evaluate out-of-distribution temporal decay in neural networks, we need an environment complex enough to break deep architectures, yet bounded enough to be solved by modern high-performance computing.
The Mancala family provides the perfect frontier. On the left, we have Awari—strongly solved by Romein and Bal in 2002. On the far right, we have Togyzkumalak, a game of immense combinatorial complexity that fundamentally resists traditional retrograde analysis. 
Bestemshe is the missing link. It shares the state-space magnitude of Awari, but possesses the deep temporal horizons of Togyzkumalak. It is the ultimate stress-test."

**Slide 3: Mapping Togyzkumalak (State-Space)** *(1:45 - 2:45)*
"Before we could solve Bestemshe, we had to formalize the mathematics of the environment. For Togyzkumalak, the literature lacked exact computational bounds. 
We did not rely on estimates. We calculated the strict bounds. 
Starting from a naive stars-and-bars distribution of ten to the twenty-fifth, we systematically applied active-game score limits, capture parity constraints, and the asymmetric rules of Tuzdyk legality. Finally, applying rotational equivalence, we derived the exact summation you see here. 
The unique active configuration space is strictly bounded at $1.51 \times 10^{25}$. To put this in perspective, this is five orders of magnitude larger than Checkers."

**Slide 4: A Billion-Game Empirical Measurement** *(2:45 - 3:45)*
"But state-space only tells us the number of board configurations. We needed to measure the game-tree complexity—the number of possible histories. 
Because pieces are irreversibly captured in these games, the branching factor decays non-linearly. Shannon’s static approximation fails here. 
To find the truth, we engineered a high-throughput C++ simulator and executed an unprecedented one-billion game Monte Carlo analysis. We captured 124.4 billion transition counters. We found that the average game length is 124 plies, yielding an empirical game-tree complexity of ten to the one-hundred-and-five ($10^{105.19}$)."

**Slide 5: Architecting the Baseline Engine** *(3:45 - 4:45)*
"To navigate this space, we required a computationally verified baseline. We engineered a highly concurrent Minimax search architecture. 
The primary bottleneck in deep search is heap fragmentation. To solve this, we architected a flat-array Transposition Table with a strict 16-byte memory layout—enforced at compile time. 
This exact alignment allows the CPU prefetcher to fetch entries with near-zero latency. It achieves 1.43 million nodes per second on a single thread and yields a 3.37x reduction in node expansion. Furthermore, we compiled this core to WebAssembly, guaranteeing zero Out-Of-Memory exceptions in browser-based RL environments."

---

### Part II: The Ground Truth (Solving Bestemshe)

**Slide 6: Architecting the 8.3GB Retrograde Oracle** *(4:45 - 6:00)*
*(Step forward. Shift your tone. This is the heavy engineering flex.)*
"With our C++ architecture verified, we turned our compute to Bestemshe. To test neural generalization, we needed an Oracle. We needed to strongly solve it. 
Mapping a ten-to-the-twelfth state space to disk requires eliminating hash table overhead. We accomplished this by deriving a colexicographical ranking bijection. 
For any given pit distribution, this equation calculates a deterministic, gap-free integer index. This allowed us to map the entire game to 169 layer files, compressed with Zstandard into just 8.3 gigabytes of $O(1)$ Win/Draw/Loss bitsets. 
Every possible game state is now a mathematical certainty."

**Slide 7: Game-Theoretic Discoveries: The Greedy Trap** *(6:00 - 7:00)*
"And the Oracle revealed that optimal play in this domain is deeply counter-intuitive. Bestemshe is a forced win for the second player. 
Look at the opening decision tree. If Player 1 plays a quiet move, Player 2 is presented with a choice. If Player 2 plays a move that instantly captures two stones, the Oracle proves they plunge into a forced loss. To maintain the mathematical win, Player 2 *must* play a quiet, non-capturing move. 
`[PAUSE. Look at the ISSAI head/professors]`
In this environment, long-term structural configuration strictly supersedes short-term material gain. This 'greedy trap' is exactly what destroys standard reinforcement learning models."

---

### Part III: The Neural Benchmark & Compounding Error

**Slide 8: Distilling the Oracle** *(7:00 - 8:00)*
"Having established absolute truth, we set out to quantify the covariate shift of neural networks. 
We distilled our 8.3 Gigabyte Oracle into a 17.2 million parameter AlphaZero-style ResMLP. Over 400,000 training steps, we exposed this network to 12.9 billion configurations. 
Crucially, the targets were generated directly from the Oracle. The network learned from mathematical ground truth, completely bypassing the noise of bootstrapped self-play."

**Slide 9: The OOD Generalization Benchmark** *(8:00 - 9:30)*
*(Let the slide appear. Let the audience read the massive numbers for 2 seconds before speaking.)*
"We then benchmarked this network against the Oracle on 2,000 matches from rare, forced-symmetric starting positions.
The model was phenomenal. It achieved a 99.69 percent optimal-move rate. Out of 226,000 decisions, it played perfectly nearly every single time.
`[PAUSE]`
And yet, despite 99.69 percent local accuracy... the network suffered a 27.8 percent game-level degradation. It threw away mathematically won or drawn positions in nearly one out of every three games."

**Slide 10: Resolving the Paradox** *(9:30 - 10:30)*
"How does a model that plays perfectly 99.69 percent of the time fail 28 percent of the time? 
The answer lies in the temporal depth of the Markov Decision Process. The average game length in this benchmark was 113 plies. In a strict game-theoretic environment, a single sub-optimal decision irreversibly collapses the state space. 
If we model this as a probabilistic decay curve, the probability of a model surviving a 113-ply trajectory without a single value-destroying blunder is $p$ to the power of $L$. 
$0.9969$ to the power of 113 is 0.696. 
`[Point to the screen]`
The math dictates a 30.4 percent theoretical failure rate. Our empirical observation of 27.8 percent aligns perfectly with this decay. The gap is simply the forgiveness of non-critical blunders."

---

### Part IV: The Conclusion & The Ask

**Slide 11: Conclusion** *(10:30 - 11:15)*
"This proves two fundamental realities for Artificial Intelligence.
First, neural networks—no matter how accurate locally—cannot unilaterally replace algorithmic search in deep-tree environments. The compounding nature of microscopic errors mathematically guarantees catastrophic global failure over long horizons.
Second, it exposes the illusion of Elo ratings. Without an Oracle, a 99 percent optimal move rate looks like superhuman intelligence. But the Oracle reveals that per-move accuracy hides total game-level collapse."

**Slide 12: Future Work** *(11:15 - 12:00)*
"Our immediate next step is leveraging unified-memory NUMA-free architectures—like Apple Silicon—to execute multi-threaded retrograde generation, with the ultimate goal of weakly solving Togyzkumalak.
By bridging low-level systems engineering, combinatorial mathematics, and deep reinforcement learning, we now have the framework to rigorously benchmark the absolute limits of AI decision-making.
My name is Ansar Zeinulla. Thank you for your time, and I welcome your questions."

