-- CreateTable
CREATE TABLE "PolicyDocument" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "agency" TEXT NOT NULL,
    "policyOrAsOfDate" TIMESTAMP(3) NOT NULL,
    "registeredAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "sectors" TEXT[],
    "tags" TEXT[],

    CONSTRAINT "PolicyDocument_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "PolicyVersion" (
    "id" TEXT NOT NULL,
    "documentId" TEXT NOT NULL,
    "versionNo" INTEGER NOT NULL,
    "fileRelPath" TEXT NOT NULL,
    "extractedText" TEXT NOT NULL,
    "summary" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PolicyVersion_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "DecisionDocument" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "meetingOrSource" TEXT NOT NULL,
    "decisionDate" TIMESTAMP(3) NOT NULL,
    "registeredAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "sectors" TEXT[],
    "tags" TEXT[],

    CONSTRAINT "DecisionDocument_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "DecisionVersion" (
    "id" TEXT NOT NULL,
    "documentId" TEXT NOT NULL,
    "versionNo" INTEGER NOT NULL,
    "fileRelPath" TEXT NOT NULL,
    "extractedText" TEXT NOT NULL,
    "summary" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DecisionVersion_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Article" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "url" TEXT,
    "fileRelPath" TEXT,
    "source" TEXT NOT NULL,
    "confirmed" BOOLEAN NOT NULL DEFAULT false,
    "confirmedAt" TIMESTAMP(3),
    "sectors" TEXT[],
    "tags" TEXT[],
    "summary" TEXT,

    CONSTRAINT "Article_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "OfficialDomain" (
    "id" TEXT NOT NULL,
    "host" TEXT NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "OfficialDomain_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "PolicyVersion_documentId_versionNo_key" ON "PolicyVersion"("documentId", "versionNo");
CREATE UNIQUE INDEX "DecisionVersion_documentId_versionNo_key" ON "DecisionVersion"("documentId", "versionNo");
CREATE UNIQUE INDEX "OfficialDomain_host_key" ON "OfficialDomain"("host");

ALTER TABLE "PolicyVersion" ADD CONSTRAINT "PolicyVersion_documentId_fkey" FOREIGN KEY ("documentId") REFERENCES "PolicyDocument"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "DecisionVersion" ADD CONSTRAINT "DecisionVersion_documentId_fkey" FOREIGN KEY ("documentId") REFERENCES "DecisionDocument"("id") ON DELETE CASCADE ON UPDATE CASCADE;
