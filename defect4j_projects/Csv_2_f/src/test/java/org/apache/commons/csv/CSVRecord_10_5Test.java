package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.lang.reflect.Constructor;
import java.util.Collections;
import java.util.Map;

import org.junit.jupiter.api.Test;

class CSVRecord_10_5Test {

    @Test
    @Timeout(8000)
    void testGetRecordNumber() throws Exception {
        String[] values = new String[] {"a", "b"};
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = "comment";
        long recordNumber = 123L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, Long.TYPE);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance((Object) values, mapping, comment, recordNumber);

        assertEquals(recordNumber, record.getRecordNumber());
    }
}