Subject: grouping tradeoff question from a small reproduction

Kush — I read your grouping post and built a small version of the decision it describes: 7 synthetic root causes with noise, four grouping strategies, scored on duplicate issues AND bad merges.

The part I didn't expect: no cosine threshold wins both columns. Under 0.85 it merges two different timeout bugs (200 events in the wrong cluster); over 0.85 it adds nothing at all, because two bugs sharing outer frames score higher than one bug with reworded messages.

Code and the sweep: https://github.com/saadsaiyed/grouping-lab

Was that tradeoff the thing that pushed you to a trained signal, or did the model solve a different failure in practice?
