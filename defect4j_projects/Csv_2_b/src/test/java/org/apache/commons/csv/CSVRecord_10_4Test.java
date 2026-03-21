package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.lang.reflect.Constructor;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

public class CSVRecord_10_4Test {

    @Test
    @Timeout(8000)
    public void testGetRecordNumber() throws Exception {
        String[] values = new String[] {"a", "b"};
        Map<String, Integer> mapping = new HashMap<>();
        String comment = "comment";
        long recordNumber = 123L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(
                String[].class, Map.class, String.class, Long.TYPE);
        constructor.setAccessible(true);
        CSVRecord csvRecord = constructor.newInstance(values, mapping, comment, recordNumber);

        assertEquals(recordNumber, csvRecord.getRecordNumber());
    }
}