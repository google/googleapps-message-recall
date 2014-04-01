# googleapps-message-recall

## Introduction

The googleapps-message-recall software is an application to be hosted on
Google AppEngine for recalling messages within a Google Apps domain.

To support scaling for large domains, the application includes a 'frontend' for
processing ui requests and a 'backend' for managing all the user tasks.  The
work is organized using AppEngine Push Queues and 'backends'.  Progress state
for the application is stored in the AppEngine NDB.

## Background

As Enterprises move to the Cloud, requirements to match pre-Cloud service
capabilities follow. One key request from Enterprises of any size has been the
ability to administratively remove an Email from all users in the domain. The
reasoning for such a request could be for Human Resource, Financial, or
Security reasons. Typically, the mail systems the Enterprises moved from had
capabilities to perform this type of “message recall”. This functionality does
not exist in Google Apps today.

The goal of this software will be to provide similar functionality given the
capabilities that exist today for domains to interact with their users
mailboxes in a scalable way using Google Cloud services.

## Getting Started

The process of setting up the message recall application includes multiple
steps.  The user must be a domain Super-Admin and will configure an AppEngine
application, the Google Apps domain and a Google Developer Console project.

The detailed instructions are included in the
[INSTALL-MESSAGE-RECALL.pdf](https://github.com/google/googleapps-message-recall/blob/master/INSTALL-MESSAGE-RECALL.pdf)
file.

## Support

For questions and answers join/view the
[googleapps-message-recall Google Group](https://groups.google.com/forum/#!forum/opensource-googleapps-message-recall).

