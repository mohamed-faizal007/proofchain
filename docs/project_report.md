PROOFCHAIN: A BLOCKCHAIN-ANCHORED
FRAMEWORK FOR VERIFIABLE DOCUMENT
PROVENANCE AND AI-ASSISTED TAMPER
LOCALIZATION
Ekanath - 23MIA1023
Mohamed Faizal - 23MIA1133
Rohan Julius Preetan - 23MIA1160
1

CHAPTER 1
INTRODUCTION
1.1 Background and Motivation
The growing reliance on digital documents such as contracts, certificates, invoices, and legal
records has made document integrity and authenticity a critical concern. Digital files can be
modified using freely available software, often without any visible trace, so verifying that a
document remains unchanged from its trusted version has become essential.
Cryptographic hashing, such as SHA-256, is the traditional approach to this problem: it
generates a unique fingerprint of a document so that any modification changes the hash value.
However, this method only produces a binary match-or-mismatch result. It cannot indicate
where a modification occurred, what was changed, whether the change was authorized, or how
the document evolved. A more comprehensive verification framework is therefore needed.
1.2 Need for Tamper Localization
Whole-document hashing cannot distinguish a single-clause edit from a complete rewrite; both
simply invalidate the hash. This creates the need for tamper localization — moving beyond
tamper detection ("Has the document changed?") to answer "Where did it change?"
Hierarchical hashing addresses this by generating additional hashes at the page, section, and
chunk level rather than only for the whole document.
Merkle Trees provide an efficient structure for this hierarchy: page or section hashes form the
leaf nodes, which combine upward into a single Merkle Root. When the root changes, the tree
can be traversed to identify exactly which branch — and therefore which region of the
document — was modified, without comparing the document contents in full each time.
1.3 Blockchain and Document Provenance
Blockchain provides a distributed, tamper-evident ledger that can anchor a document's integrity
information independently of any single centralized database. Storing complete documents on-
chain is impractical due to storage, cost, and privacy constraints, so ProofChain keeps the
document off-chain and anchors only its cryptographic and provenance metadata on-chain.
Responsibilities are divided as follows:
● AWS S3 — stores the actual document files.
● MongoDB — stores metadata, version history, and provenance records.
● Blockchain — stores integrity information (document ID, version ID, Merkle Root,
timestamp, and event data) rather than the document itself.
2

This division also lets the system distinguish authorized modifications, made through an
approved version workflow, from unauthorized ones that lack a corresponding provenance
record — since a hash mismatch alone cannot indicate whether a change was legitimate.
1.4 Role of AI and Semantic Analysis
Cryptographic and Merkle Tree verification can reliably identify that a region of a document
has changed, but not what that change means. Natural Language Processing is used after
cryptographic comparison identifies a modified region, to classify the change (for example, an
amount, date, clause, or party change).
AI does not determine document authenticity; cryptographic verification remains the
authoritative source for document integrity. AI is applied only to help users interpret and
classify changes that have already been cryptographically confirmed.
1.5 Proposed System – ProofChain
ProofChain is a cloud-native framework that integrates hierarchical SHA-256 hashing, Merkle
Trees, blockchain anchoring, document version management, and NLP-based semantic
analysis into a single pipeline:
3

A React frontend and FastAPI backend handle document intake and processing. Documents are
hierarchically hashed and organized into a Merkle Tree, with files stored in AWS S3 and
metadata in MongoDB; the resulting integrity information is anchored on the blockchain. When
verification is requested, cryptographic comparison runs first; if a mismatch is found,
hierarchical and Merkle Tree comparison localize the affected region, provenance records
confirm whether the change was authorized, and NLP analysis explains the nature of the change
on the verification dashboard.
1.6 Problem Statement and Objectives
Existing techniques verify whether a document has changed but not where the change occurred,
what was modified, whether it was authorized, or how the document evolved. Blockchain-
based methods provide tamper-evident records without fine-grained localization, and NLP
methods explain textual differences without proving authenticity. ProofChain addresses this by
integrating all of these capabilities into one framework.
The main objectives are to:
1. Implement document integrity verification using SHA-256 hashing.
2. Perform hierarchical hashing at the document, page, section, and chunk levels.
3. Use Merkle Trees for efficient tamper localization.
4. Implement blockchain anchoring for independently verifiable integrity records.
5. Maintain document metadata, provenance, and version history.
6. Distinguish authorized document versions from unauthorized modifications.
7. Use NLP to classify the semantic nature of detected changes.
1.7 Scope and Research Contribution
The current scope of ProofChain is limited to text-based PDF documents, covering integrity
verification, version tracking, provenance management, tamper localization, and semantic
change analysis. The blockchain stores only cryptographic references and event data, never the
document itself; similarly, AI is used only to explain changes after cryptographic verification
has identified them.
The key contribution of ProofChain is the integration of hierarchical cryptographic verification,
Merkle Tree-based tamper localization, blockchain-anchored provenance, document version
tracking, authorization verification, and AI-assisted semantic change analysis into a single
framework — moving document verification beyond "Has this changed?" to "What changed,
where, was it authorized, and how did the document evolve?"
4

CHAPTER 2
LITERATURE SURVEY
2.1 Introduction
Document verification has been studied separately through cryptographic hashing, Merkle Tree
structures, blockchain anchoring, and NLP-based semantic comparison. This survey reviews
recent work in each of these areas and identifies the research gap that ProofChain is designed to
address: no existing framework combines fine-grained cryptographic localization, blockchain
provenance, and semantic interpretation in one system.
2.2 Cryptographic and Merkle Tree-Based Verification
Boonkrong (2024) demonstrates that SHA-256-based hashing reliably detects whether an
academic document has been altered, but like all whole-document hashing schemes, it returns
only a match-or-mismatch result without indicating where a change occurred. Complementary
work on adaptive Merkle trees (2024) shows that restructuring the tree dynamically improves
verification efficiency and scalability for large datasets, and this hierarchical structure is
directly applicable to localizing changes within a document rather than only within blockchain
transaction sets. However, neither line of work provides any semantic understanding of what a
detected change represents.
Research Gap: Existing cryptographic and Merkle Tree approaches provide integrity
verification but have limited semantic understanding and authorization-aware document
analysis.
2.3 Blockchain-Based Document Verification and Provenance
MerkleDoc (Patil et al., 2025) combines Merkle trees with blockchain anchoring to provide
privacy-preserving, tamper-evident document verification, while Mishra and Ganesan (2025,
Frontiers in Blockchain; 2025, Scientific Reports) propose blockchain-anchored, policy-
governed frameworks that detect shadow and incremental-update attacks on digitally signed
PDFs using keyless signature infrastructure. These studies confirm that blockchain anchoring
produces independently verifiable, tamper-evident integrity records without requiring on-chain
storage of the full document. However, none of them localize which specific region of a
document was altered, nor do they track authorized version transitions over a document's
lifecycle.
Research Gap: Blockchain can provide independently verifiable integrity records but does not
automatically provide fine-grained tamper localization or semantic interpretation.
2.4 NLP-Based Semantic Document Comparison
5

De Oliveira and Nascimento (2025) use transformer models (BERT, GPT-2, RoBERTa, and
LLaMA) to measure semantic similarity between legal court documents with high accuracy,
while Rykov et al. (2026) use large language models for fine-grained, categorized comparison
of legal document revisions, distinguishing changes such as amount, date, and clause
modifications. Both confirm that modern NLP techniques can meaningfully classify the nature
of textual changes. However, semantic similarity scoring provides no cryptographic guarantee
that a document is authentic or unmodified outside the regions being compared.
Research Gap: NLP can explain document changes but cannot cryptographically prove
document authenticity.
2.5 Comparative Analysis
| Paper / Study               | Year                    | Approach | Main Contribution          | Limitation         |
| --------------------------- | ----------------------- | -------- | -------------------------- | ------------------ |
| Design of an Academic       |                         |          |                            | Cannot localize    |
|                             | SHA-256                 |          | Reliable digital document  |                    |
| Document Forgery Detection  | 2024                    |          |                            | where changes      |
|                             | cryptographic hashing   |          | integrity verification     |                    |
| System (Boonkrong)          |                         |          |                            | occurred           |
| Adaptive Merkle Trees for   |                         |          |                            | Limited semantic   |
|                             | Adaptive, restructured  |          | Improved hierarchical      |                    |
| Enhanced Blockchain         | 2024                    |          |                            | interpretation of  |
|                             | Merkle tree hashing     |          | verification efficiency    |                    |
| Scalability                 |                         |          |                            | changes            |
MerkleDoc: A Privacy-
|     | Merkle tree +  |     | Privacy-preserving, tamper- | No authorization- |
| --- | -------------- | --- | --------------------------- | ----------------- |
Preserving Blockchain-Based
|     | 2025 blockchain hybrid  |     | evident document  | aware version  |
| --- | ----------------------- | --- | ----------------- | -------------- |
Document Verification
|     | verification |     | verification | tracking |
| --- | ------------ | --- | ------------ | -------- |
System (Patil et al.)
Securing E-Governance: A
Blockchain-Based Framework  Blockchain hash  Detects shadow and  Limited fine-
for Tamper-Proof PDF  2025 anchoring with policy- incremental-update attacks  grained tamper
Document Exchange (Mishra  based governance on signed PDFs localization
& Ganesan)
Securing E-Governance
|                              | Blockchain validation        |     |                           | Does not localize  |
| ---------------------------- | ---------------------------- | --- | ------------------------- | ------------------ |
| Against Shadow Attacks with  |                              |     | Independently verifiable  |                    |
|                              | 2025 with keyless signature  |     |                           | tampered regions   |
| Blockchain Technology        |                              |     | PDF integrity records     |                    |
|                              | infrastructure               |     |                           | within a document  |
(Mishra & Ganesan)
Analysing Similarities
| Between Legal Court          |                   |     |                                | Cannot             |
| ---------------------------- | ----------------- | --- | ------------------------------ | ------------------ |
|                              | BERT, GPT-2,      |     | High-accuracy semantic         |                    |
| Documents Using NLP          |                   |     |                                | cryptographically  |
|                              | 2025 RoBERTa and  |     | similarity detection in legal  |                    |
| Approaches Based on          |                   |     |                                | prove document     |
|                              | LLaMA embeddings  |     | text                           |                    |
| Transformers (de Oliveira &  |                   |     |                                | authenticity       |
Nascimento)
Fine-Grained Semantic
|                       | LLM-based fine-          |     | Detailed, annotated  |                  |
| --------------------- | ------------------------ | --- | -------------------- | ---------------- |
| Comparison of Legal   |                          |     |                      | No blockchain-   |
|                       | 2026 grained comparison  |     | document change      |                  |
| Documents Using LLMs  |                          |     |                      | based provenance |
|                       | pipeline                 |     | classification       |                  |
(Rykov et al.)
2.6 Research Gap and ProofChain Contribution
6

Across the reviewed literature, cryptographic integrity verification, Merkle Tree-based
localization, blockchain provenance, document versioning, and semantic analysis are
consistently treated as separate problems, each addressed by a different family of techniques.
There is limited research on a unified framework that combines fine-grained
cryptographic tamper localization, blockchain-anchored provenance, authorized
document version tracking, and AI-assisted semantic change analysis.
ProofChain addresses this gap by integrating all five capabilities into a single sequential
pipeline: cryptographic comparison first determines whether a document has changed;
hierarchical hashing and Merkle Tree comparison then localize the affected page, section, or
chunk; provenance and version records determine whether the change was authorized; and
NLP-based analysis finally classifies and explains the nature of the change. This integration is
what distinguishes ProofChain from prior work, which typically addresses only one stage of
this pipeline in isolation.
REFERENCES
[1] S. Boonkrong, "Design of an Academic Document Forgery Detection System,"
International Journal of Information Technology, 2024.
[2] "Adaptive Merkle Trees for Enhanced Blockchain Scalability," Blockchain: Research and
Applications (ScienceDirect), 2024.
[3] A. Patil et al., "MerkleDoc: A Privacy-Preserving Blockchain-Based Document
Verification System," 2025.
[4] P. Mishra and R. Ganesan, "Securing E-Governance: A Blockchain-Based Framework for
Tamper-Proof PDF Document Exchange," Frontiers in Blockchain, 2025.
[5] P. Mishra and R. Ganesan, "Securing E-Governance Against Shadow Attacks with
Blockchain Technology," Scientific Reports, 2025.
[6] R. S. de Oliveira and E. G. S. Nascimento, "Analysing Similarities Between Legal Court
Documents Using Natural Language Processing Approaches Based on Transformers," PLOS
ONE, 2025.
[7] E. Rykov et al., "Fine-Grained Semantic Comparison of Legal Documents Using LLMs,"
Proceedings of ACL 2026 (Student Research Workshop), 2026.
7