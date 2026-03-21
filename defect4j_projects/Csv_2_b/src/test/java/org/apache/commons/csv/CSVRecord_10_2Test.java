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

public class CSVRecord_10_2Test {

    @Test
    @Timeout(8000)
    void testGetRecordNumber() throws Exception {
        String[] values = new String[] {"value1", "value2"};
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = "comment";
        long recordNumber = 123L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        long result = record.getRecordNumber();

        assertEquals(recordNumber, result);
    }
}